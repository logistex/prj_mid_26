# 2026-10-31 11:16 KST
"""연습 시나리오 실행 페이지의 순수 논리(PRD_step4). 화면과 DB를 모름

단계표 CSV 읽기와 검사, 하위 단계 나누기, 건너뜀 규칙, 판정, 전후 비교, 배정안 얹기, AI 호출 한도 계산을 함.
이 모듈에는 어떤 시나리오의 학번, 이름, 단계 번호도 쓰지 않음(중간과제 공고 6.3절 감점 19번). 단계표는 관리자가 올린 파일에서만 읽음
"""
import copy
import csv
import io
from dataclasses import dataclass

STATUSES = ("승인", "대기", "거절", "막힘")
ACTIONS = ("지원", "투표", "마감", "배정", "확정")
ADMIN_ACTIONS = ("마감", "배정", "확정")
CHOICES = ("찬성", "거부")
HEADER = ["step", "action", "actor", "team_no", "target", "choice", "expected", "note"]
MAX_ROWS = 200
MAX_BYTES = 200 * 1024

# AI 호출 한도(중간과제 공고 4.3절): 무료 모델은 하루 50회, 채점 기간에는 30회 이상을 남겨 둠, 배정 1번에 최대 3회
DAILY_LIMIT = 50
RESERVE = 30
CALLS_PER_RUN = 3

PHASE_LABEL = {None: "명단이 올라오지 않음", "open": "모집 중", "closed": "모집 마감", "confirmed": "배정 확정"}


class StepTableError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


@dataclass(frozen=True)
class Action:
    """실행에 쓰는 값만 담음. 기대 결과와 설명은 담지 않음(실행이 기대 결과를 볼 수 없게 함)"""
    action: str
    actor: str = ""
    team_no: int = None
    target: str = ""
    choice: str = ""


@dataclass(frozen=True)
class Row:
    line: int
    step: int
    action: str
    actor: str
    team_no: int
    target: str
    choice: str
    expected: str
    note: str

    def to_action(self):
        return Action(self.action, self.actor, self.team_no, self.target, self.choice)


@dataclass(frozen=True)
class Unit:
    """좌측 목록의 1줄: 같은 step의 행 가운데 이어진 지원과 투표의 묶음, 또는 관리자 동작 1개"""
    label: str
    step: int
    rows: tuple

    @property
    def key(self):
        return self.label.replace("-", "_")

    @property
    def note(self):
        return " / ".join(r.note for r in self.rows if r.note)

    @property
    def kind(self):
        first = self.rows[0].action
        return first if first in ADMIN_ACTIONS else "지원과 투표"


# ---- 단계표 CSV ----

def _int(text):
    try:
        return int(text)
    except ValueError:
        return None


def parse_steps(data):
    """CSV 바이트를 [Row]로 바꿈. 어긋난 곳을 모두 모아 StepTableError로 알림. BOM이 있어도 읽음"""
    if len(data) > MAX_BYTES:
        raise StepTableError([f"파일이 {MAX_BYTES // 1024}KB보다 큼"])
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise StepTableError(["파일이 UTF-8이 아님"])
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        raise StepTableError(["단계표 파일이 비어 있음"])
    if [h.strip() for h in header] != HEADER:
        raise StepTableError(["열이 " + ",".join(HEADER) + "가 아님"])

    errors, rows = [], []
    for cells in reader:
        n = reader.line_num
        if not any(c.strip() for c in cells):
            continue
        if len(cells) != len(HEADER):
            errors.append(f"{n}줄: 열 수가 {len(HEADER)}개가 아님")
            continue
        step_t, action, actor, team_t, target, choice, expected, note = (c.strip() for c in cells)
        problems = []
        step = _int(step_t)
        if step is None or step < 1:
            problems.append("step이 1 이상의 정수가 아님")
        if action not in ACTIONS:
            problems.append(f"action이 {', '.join(ACTIONS)} 가운데 하나가 아님")
        if expected and expected not in STATUSES:
            problems.append(f"expected가 {', '.join(STATUSES)} 가운데 하나가 아님")
        team_no = None
        if team_t:
            team_no = _int(team_t)
            if team_no is None or team_no < 1:
                problems.append("team_no가 1 이상의 정수가 아님")
        if action == "지원":
            if not actor:
                problems.append("지원에는 actor가 필요함")
            if not team_t:
                problems.append("지원에는 team_no가 필요함")
        elif action == "투표":
            if not actor:
                problems.append("투표에는 actor가 필요함")
            if not target:
                problems.append("투표에는 target이 필요함")
            if choice not in CHOICES:
                problems.append(f"투표의 choice가 {', '.join(CHOICES)} 가운데 하나가 아님")
        elif action in ADMIN_ACTIONS:
            if actor or team_t or target or choice:
                problems.append(f"{action} 동작에는 actor, team_no, target, choice를 쓰지 않음")
        if action == "지원" and (target or choice):
            problems.append("지원에는 target과 choice를 쓰지 않음")
        if action == "투표" and team_t:
            problems.append("투표에는 team_no를 쓰지 않음")
        if problems:
            errors.extend(f"{n}줄: {p}" for p in problems)
            continue
        rows.append(Row(n, step, action, actor, team_no, target, choice, expected, note))

    if len(rows) + len(errors) > MAX_ROWS:
        errors.append(f"행이 {MAX_ROWS}개를 넘음")
    previous = 0
    for row in rows:
        if row.step != previous and row.step != previous + 1:
            errors.append(f"{row.line}줄: step 번호가 이어지지 않음(앞 행이 {previous}이면 {previous} 또는 {previous + 1}이어야 함)")
            break
        previous = row.step
    if not rows and not errors:
        errors.append("단계표에 행이 없음")
    if errors:
        raise StepTableError(errors)
    return rows


def check_against_roster(rows, student_nos, team_count):
    """단계표의 학번이 명단에 있고 팀 번호가 팀 수 이하인지. 어긋난 곳의 목록(없으면 [])"""
    errors = []
    for r in rows:
        for who, no in (("actor", r.actor), ("target", r.target)):
            if no and no not in student_nos:
                errors.append(f"{r.line}줄: {who} {no}가 명단에 없음")
        if r.team_no is not None and r.team_no > team_count:
            errors.append(f"{r.line}줄: 팀 번호 {r.team_no}가 팀 수 {team_count}보다 큼")
    return errors


def split_units(rows):
    """같은 step의 행을 하위 단계로 나눔. 마감, 배정, 확정 행은 행마다 독립한 하위 단계이고,
    그 사이에 이어진 지원과 투표 행은 1개의 하위 단계임. 하위 단계가 2개 이상인 step은 번호를 N-1, N-2로 붙임"""
    by_step = {}
    for r in rows:
        by_step.setdefault(r.step, []).append(r)
    units = []
    for step, step_rows in by_step.items():
        groups, current = [], []
        for r in step_rows:
            if r.action in ADMIN_ACTIONS:
                if current:
                    groups.append(current)
                    current = []
                groups.append([r])
            else:
                current.append(r)
        if current:
            groups.append(current)
        for i, g in enumerate(groups, start=1):
            label = str(step) if len(groups) == 1 else f"{step}-{i}"
            units.append(Unit(label, step, tuple(g)))
    return units


# ---- 건너뜀 규칙과 판정 ----

class SkipTracker:
    """지원이 막혔으면 그 지원에 대한 뒤의 투표는 건너뜀(중간과제 공고 부록). 실제 결과로만 정함"""

    def __init__(self):
        self.blocked = set()

    def should_skip(self, action):
        return action.action == "투표" and action.target in self.blocked

    def note_result(self, action, status):
        if action.action == "지원" and status == "막힘":
            self.blocked.add(action.actor)


def judge(expected, status, skipped=False):
    if skipped:
        return "건너뜀"
    if not expected:
        return "비교 없음"
    return "일치" if status == expected else "불일치"


def judge_unit(verdicts):
    if "불일치" in verdicts:
        return "불일치"
    if "일치" in verdicts:
        return "일치"
    return "비교 없음"


def verdicts(rows, record):
    """기록의 행별 실제 결과를 단계표의 기대 결과와 비교함. 실행이 끝난 뒤에만 부름"""
    return [judge(r.expected, rr["status"], rr["skipped"]) for r, rr in zip(rows, record.get("rows", []))]


def unit_states(units, records, running=None):
    """하위 단계마다 상태: 실행함, 다음 차례, 대기, 중단됨"""
    states, blocked = [], False
    for u in units:
        rec = records.get(u.label)
        if rec is not None and "error" not in rec and "denied" not in rec:
            states.append("실행함")
        elif blocked:
            states.append("대기")
        elif rec is not None or running == u.label:
            states.append("중단됨")
            blocked = True
        else:
            states.append("다음 차례")
            blocked = True
    return states


# ---- 전후 비교 ----

@dataclass(frozen=True)
class Change:
    kind: str
    team_no: int = None
    student_no: str = None
    name: str = ""
    detail: str = ""


def _yes(person):
    return sum(1 for v in person.get("votes", {}).values() if v == "찬성")


def diff_views(before, after):
    changes = []
    if before["phase"] != after["phase"]:
        changes.append(Change("단계 변화", detail=f"{PHASE_LABEL.get(before['phase'], before['phase'])} → "
                                                  f"{PHASE_LABEL.get(after['phase'], after['phase'])}"))
    bt = {t["team_no"]: t for t in before["teams"]}
    at = {t["team_no"]: t for t in after["teams"]}
    for team_no in sorted(set(bt) | set(at)):
        b = bt.get(team_no, {"members": [], "pending": []})
        a = at.get(team_no, {"members": [], "pending": []})
        bm = {m["student_no"]: m for m in b["members"]}
        am = {m["student_no"]: m for m in a["members"]}
        for no in sorted(am.keys() - bm.keys()):
            changes.append(Change("새 팀원", team_no, no, am[no]["name"]))
        for no in sorted(bm.keys() - am.keys()):
            changes.append(Change("빠진 팀원", team_no, no, bm[no]["name"]))
        bp = {p["student_no"]: p for p in b["pending"]}
        ap = {p["student_no"]: p for p in a["pending"]}
        for no in sorted(ap.keys() - bp.keys()):
            changes.append(Change("대기 지원 생김", team_no, no, ap[no]["name"]))
        for no in sorted(bp.keys() - ap.keys()):
            changes.append(Change("대기 지원 없어짐", team_no, no, bp[no]["name"]))
        for no in sorted(ap.keys() & bp.keys()):
            if _yes(ap[no]) != _yes(bp[no]):
                detail = f"찬성 {_yes(bp[no])}/{len(b['members'])} → {_yes(ap[no])}/{len(a['members'])}"
                changes.append(Change("찬성 수 변화", team_no, no, ap[no]["name"], detail))
    bu = {u["student_no"]: u for u in before["unassigned"]}
    au = {u["student_no"]: u for u in after["unassigned"]}
    for no in sorted(au.keys() - bu.keys()):
        changes.append(Change("팀이 없는 학생 생김", None, no, au[no]["name"]))
    for no in sorted(bu.keys() - au.keys()):
        changes.append(Change("팀이 없는 학생 없어짐", None, no, bu[no]["name"]))
    return changes


def is_discontinuous(previous, current):
    """앞 하위 단계가 끝난 뒤의 DB 상태와 이 하위 단계를 실행하기 직전의 상태가 다르면 True(다른 곳에서 DB가 바뀜)"""
    return bool(diff_views(previous["after_db"], current["before"]))


def apply_proposal(view, pairs):
    """배정안(학번, 팀 번호)을 팀에 얹은 새 상태. 얹은 학생에는 proposed 표시를 하고 원본은 바꾸지 않음"""
    out = copy.deepcopy(view)
    waiting = {u["student_no"]: u for u in out["unassigned"]}
    teams = {t["team_no"]: t for t in out["teams"]}
    for student_no, team_no in pairs:
        student = waiting.pop(student_no, None)
        if student is None or team_no not in teams:
            continue
        student["proposed"] = True
        teams[team_no]["members"].append(student)
    out["unassigned"] = list(waiting.values())
    return out


# ---- AI 호출 한도 ----

@dataclass(frozen=True)
class Quota:
    used: int
    blocked: bool
    warn: bool
    remaining_after: int


def quota(used):
    """오늘 기록이 used회일 때 모델 호출을 막을지(이 실행이 하루 한도를 넘김), 채점 기간의 보존 횟수를 침범한다고 경고할지"""
    remaining_after = DAILY_LIMIT - used - CALLS_PER_RUN
    blocked = used + CALLS_PER_RUN > DAILY_LIMIT
    return Quota(used, blocked, (not blocked) and remaining_after < RESERVE, remaining_after)


def md_escape(text):
    """학생 이름과 안내 글이 마크다운 서식으로 읽히지 않게 함"""
    return "".join("\\" + c if c in "\\`*_[]<>~$:" else c for c in str(text))
