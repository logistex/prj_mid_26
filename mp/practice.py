# 2026-10-31 11:16 KST
"""연습 시나리오 실행 페이지의 순수 논리(PRD_step4). 화면과 DB를 모름

단계표 CSV 읽기와 검사, 하위 단계 나누기, 건너뜀 규칙, 판정, 전후 비교, 배정안 얹기, AI 호출 한도 계산을 함.
이 모듈에는 어떤 시나리오의 학번, 이름, 단계 번호도 쓰지 않음(중간과제 공고 6.3절 감점 19번). 단계표는 관리자가 올린 파일에서만 읽음
"""
import copy
import csv
import io
import re
from dataclasses import dataclass, field

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


# ---- 시간 줄과 상황 설명(PRD_step4 4.2절) ----

_FINAL_BY_DIGIT = {"0": True, "1": True, "2": False, "3": True, "4": False, "5": False, "6": True, "7": True, "8": True, "9": False}


def short_name(name):
    """명단의 이름 끝에 붙은 괄호(예: 이름(역할 약자))를 떼어 시간 줄과 설명에 짧게 씀. 괄호가 없으면 그대로임"""
    text = re.sub(r"\s*\([^()]*\)\s*$", "", str(name)).strip()
    return text or str(name)


def has_final(text):
    """마지막 글자에 받침이 있으면 True, 없으면 False, 알 수 없으면 None(한글과 숫자만 앎)"""
    last = str(text)[-1:]
    if not last:
        return None
    if "가" <= last <= "힣":
        return (ord(last) - ord("가")) % 28 != 0
    return _FINAL_BY_DIGIT.get(last)


def josa(text, with_final, without_final):
    final = has_final(text)
    if final is None:
        return f"{text}{with_final}({without_final})"
    return text + (with_final if final else without_final)


def subject(text):
    return josa(text, "이", "가")


def topic(text):
    return josa(text, "은", "는")


@dataclass
class Outcome:
    """하위 단계 안에서 일어난 지원 1건의 경과. 실제 실행 결과(기록)로만 채움"""
    student_no: str
    team_no: int
    status: str
    applied: bool
    first_status: str = ""
    first_message: str = ""
    votes: list = field(default_factory=list)


def application_outcomes(rows, record_rows):
    """하위 단계의 행과 그 실행 기록(rows)에서 지원마다 경과를 모음. 건너뛴 행과 막힌 투표는 넣지 않음"""
    outcomes = {}
    for row, rr in zip(rows, record_rows):
        if rr.get("skipped"):
            continue
        if row.action == "지원":
            outcomes[row.actor] = Outcome(row.actor, row.team_no, rr["status"], True, rr["status"], rr["message"])
        elif row.action == "투표":
            if rr["status"] == "막힘":
                continue
            o = outcomes.get(row.target)
            if o is None:
                o = outcomes[row.target] = Outcome(row.target, None, "", False)
            o.votes.append((row.actor, row.choice))
            o.status = rr["status"]
    return list(outcomes.values())


def summarize_unit(unit, name_of):
    """시간 줄의 한 줄 요약. 예: 학생7이 팀1에 지원, 학생1 찬성, 학생4 거부"""
    kind = unit.kind
    if kind == "마감":
        return "모집 마감"
    if kind == "배정":
        return "AI 배정"
    if kind == "확정":
        return "배정 확정"
    applied = {r.actor for r in unit.rows if r.action == "지원"}
    parts = []
    for r in unit.rows:
        if r.action == "지원":
            parts.append(f"{subject(name_of(r.actor))} 팀{r.team_no}에 지원")
        elif r.target in applied:
            parts.append(f"{name_of(r.actor)} {r.choice}")
        else:
            parts.append(f"{subject(name_of(r.actor))} {name_of(r.target)}에 {r.choice}")
    return ", ".join(parts)


def unit_result(unit, record):
    """시간 줄의 결과 배지: 건너뛰지 않은 마지막 행의 실제 결과. 모두 건너뛰었으면 건너뜀"""
    statuses = [rr["status"] for rr in record.get("rows", []) if not rr.get("skipped")]
    return statuses[-1] if statuses else "건너뜀"


def team_of(view, student_no):
    """학생의 대기 지원이나 팀원 자리가 있는 팀 번호. 없으면 None"""
    for t in view["teams"]:
        if any(p["student_no"] == student_no for p in t["pending"]) or any(m["student_no"] == student_no for m in t["members"]):
            return t["team_no"]
    return None


def narrate(unit, record, name_of):
    """그 단계에서 일어난 일을 한 문장으로. 실제 실행 결과(기록)와 전후 상태로만 씀"""
    rrs = record.get("rows", [])
    if unit.kind != "지원과 투표":
        head = {"마감": "모집 마감", "배정": "AI 배정", "확정": "배정 확정"}[unit.kind]
        rr = rrs[0] if rrs else {"status": "", "message": ""}
        return f"{head} → {rr['status']}: {rr['message']}"
    before, after = record["before"], record["after"]
    changes = diff_views(before, after)
    team_changed = {c.team_no for c in changes if c.kind in ("새 팀원", "빠진 팀원")}
    size_before = {t["team_no"]: len(t["members"]) for t in before["teams"]}
    sentences = []
    for o in application_outcomes(unit.rows, rrs):
        who = name_of(o.student_no)
        team_no = o.team_no or team_of(before, o.student_no) or team_of(after, o.student_no)
        seq = []
        if o.applied:
            seq.append(f"{subject(who)} 팀{o.team_no}에 지원함")
            if o.first_status == "막힘":
                seq.append(f"막힘: {o.first_message}")
            elif o.first_status == "승인":
                seq.append("바로 승인되어 팀원이 됨")
            elif o.first_status == "대기":
                seq.append(f"팀원 {size_before.get(o.team_no, 0)}명의 투표를 기다림")
        elif o.votes:
            seq.append(f"{topic(who)} 팀{team_no}에 낸 지원에 투표가 있었음")
        if o.votes:
            seq.append(", ".join(f"{name_of(v)} {c}" for v, c in o.votes))
            if o.status == "승인":
                seq.append(f"승인. {subject(who)} 팀{team_no}의 팀원이 됨")
            elif o.status == "거절":
                kept = f"{topic(f'팀{team_no}')} 그대로이고 " if team_no not in team_changed else ""
                seq.append(f"거절. {kept}{topic(who)} 팀이 없는 학생으로 돌아감")
            else:
                seq.append("아직 결과가 나지 않음")
        sentences.append(" → ".join(seq))
    return " / ".join(sentences) if sentences else "일어난 일이 없음"


@dataclass(frozen=True)
class Progress:
    total: int
    done: int
    partial: int = None


def progress(units, states):
    """단계표의 단계(step) 번호 기준 진행. 하위 단계가 모두 실행된 단계만 끝난 것으로 셈"""
    steps = list(dict.fromkeys(u.step for u in units))
    done, partial = 0, None
    for s in steps:
        mine = [st_ for u, st_ in zip(units, states) if u.step == s]
        if all(x == "실행함" for x in mine):
            done += 1
        elif any(x == "실행함" for x in mine):
            partial = s
    return Progress(len(steps), done, partial)


def progress_text(p):
    text = f"{p.total}단계 가운데 {p.done}단계까지 실행함"
    return text + (f"({p.partial}단계는 일부만 실행함)" if p.partial is not None else "")


def scenario_title(filename):
    """올린 단계표 파일 이름에서 시나리오 이름을 만듦. 파일 이름에서 확장자와 끝의 단계 낱말을 뗌"""
    stem = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    if stem.lower().endswith(".csv"):
        stem = stem[:-4]
    stem = re.sub(r"[\s_-]*단계$", "", stem).strip()
    return f"{stem} 시나리오" if stem else "시나리오"


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
