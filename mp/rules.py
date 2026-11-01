# 2026-10-30 22:40 KST
"""팀 규칙. DB를 만지지 않는 순수 함수(PRD_step2 3장). 학생은 {id, main_role, sub_roles}를 가진 dict임"""
import re
import time

MAX_TEAM_SIZE = 4
REQUIRED_ROLES = ("기획자", "웹 프로그래머")


def roles_of(student):
    """학생 1명이 맡을 수 있는 역할 집합: 주 역할과 보조 역할의 합집합"""
    return {student["main_role"], *student["sub_roles"]}


def required_deficit(students):
    """필수 포함 역할(기획자, 웹 프로그래머) 2개 가운데 아직 채우지 못한 수.

    두 역할은 서로 다른 학생이 맡아야 하므로, 1명이 둘 다 맡을 수 있어도 1개만 채움
    """
    planners = {s["id"] for s in students if REQUIRED_ROLES[0] in roles_of(s)}
    webs = {s["id"] for s in students if REQUIRED_ROLES[1] in roles_of(s)}
    both = planners | webs
    if planners and webs and len(both) >= 2:
        filled = 2
    elif both:
        filled = 1
    else:
        filled = 0
    return 2 - filled


def join_violation(members, applicant):
    """applicant가 members의 팀에 들어갈 때 어기는 첫 규칙의 이유. 어기지 않으면 None

    PRD_step2 4.1절의 검사 순서: R1(정원), R2(주 역할 중복), R3(필수 포함 역할 점검)
    """
    if len(members) >= MAX_TEAM_SIZE:
        return "팀이 꽉 참"
    if any(m["main_role"] == applicant["main_role"] for m in members):
        return "같은 주 역할의 팀원이 있음"
    after = [*members, applicant]
    if required_deficit(after) > MAX_TEAM_SIZE - len(after):
        return "필수 포함 역할(기획자, 웹 프로그래머)을 맡을 학생의 자리가 모자람"
    return None


# ---- 3단계: 배정 검사와 규칙을 지키는 배정 찾기(PRD_step3 4장) ----
MIN_TEAM_SIZE = 2


def _team_label(team_no):
    return f"팀{team_no}"


def _person_label(student):
    """학생 1명을 가리키는 글: 이름(끝의 괄호는 뺌), 이름이 없으면 학번"""
    name = re.sub(r"\s*\([^)]*\)\s*$", "", str(student.get("name") or ""))
    return name or str(student.get("student_no", student.get("id")))


def _team_with(team_no, members):
    """어긴 팀을 팀원과 함께 가리키는 글. 예: 팀2(학생5, 학생6)"""
    return f"{_team_label(team_no)}({', '.join(_person_label(m) for m in members) or '팀원 없음'})"


def _all_bad(grown, test, message):
    """팀마다 test(팀원)가 None이 아니면 어긴 것임. 어긴 팀을 모두 모아 (설명, 통과 여부)를 돌려줌"""
    found = []
    for team_no in sorted(grown):
        problem = test(grown[team_no])
        if problem is not None:
            found.append(message(team_no, grown[team_no], problem))
    return "; ".join(found), not found


def _size_problem(members):
    return None if MIN_TEAM_SIZE <= len(members) <= MAX_TEAM_SIZE else len(members)


def _size_message(team_no, members, count):
    return f"{_team_with(team_no, members)}은 {count}명임(2~4명이어야 함)"


def _same_main_problem(members):
    roles = {}
    for m in members:
        roles.setdefault(m["main_role"], []).append(m)
    same = {role: group for role, group in roles.items() if len(group) > 1}
    return same or None


def _same_main_message(team_no, members, same):
    return "; ".join(f"{_team_label(team_no)}에서 {', '.join(_person_label(m) for m in group)}의 주 역할이 {role}로 같음"
                     for role, group in same.items())


def _required_problem(members):
    return True if required_deficit(members) > 0 else None


def _required_message(team_no, members, _):
    return f"{_team_with(team_no, members)}의 필수 포함 역할(기획자, 웹 프로그래머)을 채울 수 없음"


def check_assignment(teams, unassigned, pairs):
    """배정안 검사 5가지(공고 2.5절 4항). 통과하면 None, 어기면 '검사 N번: 이유'

    teams: [{team_no, members:[학생 dict]}], unassigned: 팀이 없는 학생 dict 목록(student_no 포함),
    pairs: [(student_no, team_no), ...]. 학생 dict는 {id, student_no, main_role, sub_roles}
    """
    wanted = {s["student_no"] for s in unassigned}
    seen = set()
    for student_no, _ in pairs:
        if student_no in seen:
            return "검사 2번: 한 학생이 두 번 이상 배정됨"
        seen.add(student_no)
    team_nos = {t["team_no"] for t in teams}
    if seen - wanted:
        return "검사 1번: 팀이 없는 학생이 아닌 학번이 들어 있음"
    if wanted - seen:
        return "검사 1번: 배정되지 않은 학생이 있음"
    if any(team_no not in team_nos for _, team_no in pairs):
        return "검사 2번: 없는 팀 번호가 들어 있음"

    by_no = {s["student_no"]: s for s in unassigned}
    grown = {t["team_no"]: list(t["members"]) for t in teams}
    for student_no, team_no in pairs:
        grown[team_no].append(by_no[student_no])
    for team_no in sorted(grown):  # 검사 3번: 모든 팀이 2~4명
        n = len(grown[team_no])
        if not MIN_TEAM_SIZE <= n <= MAX_TEAM_SIZE:
            return f"검사 3번: {_team_label(team_no)}의 인원이 {n}명임(2~4명이어야 함)"
    for team_no in sorted(grown):  # 검사 4번: 팀 안에서 주 역할 중복 없음
        mains = [m["main_role"] for m in grown[team_no]]
        if len(set(mains)) != len(mains):
            return f"검사 4번: {_team_label(team_no)}에 주 역할이 같은 학생이 있음"
    for team_no in sorted(grown):  # 검사 5번: 필수 포함 역할을 실제로 채움
        if required_deficit(grown[team_no]) > 0:
            return f"검사 5번: {_team_label(team_no)}에 필수 포함 역할(기획자, 웹 프로그래머)을 채울 수 없음"
    return None


def assignment_checks(teams, unassigned, pairs):
    """배정안 검사 5가지를 각각 따로 계산함(PRD_step4 3.4절). [{no, title, ok, detail}] 5개

    check_assignment는 처음 어긴 1가지만 알려 주고, 이 함수는 5가지의 통과 여부를 모두 알려 줌.
    check_assignment가 통과(None)이면 5가지 모두 통과이고, 그 반대도 같음
    """
    wanted = {s["student_no"] for s in unassigned}
    by_no = {s["student_no"]: s for s in unassigned}
    team_nos = {t["team_no"] for t in teams}
    counts = {}
    for student_no, _ in pairs:
        counts[student_no] = counts.get(student_no, 0) + 1
    assigned = set(counts)
    out = []

    def add(title, ok, detail):
        out.append({"no": len(out) + 1, "title": title, "ok": ok, "detail": "통과" if ok else detail})

    parts = []
    if assigned - wanted:
        parts.append(f"팀이 없는 학생이 아닌 학번이 들어 있음({', '.join(sorted(assigned - wanted))})")
    if wanted - assigned:
        parts.append(f"배정되지 않은 학생이 있음({', '.join(_person_label(by_no[no]) for no in sorted(wanted - assigned))})")
    add("팀이 없는 학생이 빠짐없이 배정되고, 그 밖의 학번은 없음", assigned == wanted, "; ".join(parts))
    dup = sorted(no for no, c in counts.items() if c > 1)
    bad_team = sorted({team_no for _, team_no in pairs if team_no not in team_nos})
    parts = []
    if dup:
        parts.append(f"한 학생이 두 번 이상 배정됨({', '.join(_person_label(by_no.get(no, {'student_no': no})) for no in dup)})")
    if bad_team:
        parts.append(f"없는 팀 번호가 들어 있음({', '.join(_team_label(n) for n in bad_team)})")
    add("한 학생이 1번만 배정되고 팀 번호가 있는 팀임", not dup and not bad_team, "; ".join(parts))

    grown = {t["team_no"]: list(t["members"]) for t in teams}
    placed = set()
    for student_no, team_no in pairs:  # 앞의 2가지를 어긴 배정은 5가지를 따로 보여 주기 위해 올바른 쌍만 얹음
        if student_no in by_no and team_no in grown and student_no not in placed:
            placed.add(student_no)
            grown[team_no].append(by_no[student_no])

    detail, ok = _all_bad(grown, _size_problem, _size_message)
    add("배정한 뒤 모든 팀이 2~4명임", ok, detail)
    detail, ok = _all_bad(grown, _same_main_problem, _same_main_message)
    add("팀 안에 주 역할이 같은 학생이 없음", ok, detail)
    detail, ok = _all_bad(grown, _required_problem, _required_message)
    add("모든 팀이 필수 포함 역할(기획자, 웹 프로그래머)을 채울 수 있음", ok, detail)
    return out


def final_state_checks(teams, unassigned):
    """확정한 팀 구성의 규칙 확인 4가지(PRD_step4 3.4절). [{no, title, ok, detail}] 4개

    teams: [{team_no, members:[학생 dict]}], unassigned: 팀이 없는 학생 목록
    """
    out = []

    def add(title, ok, detail):
        out.append({"no": len(out) + 1, "title": title, "ok": ok, "detail": "통과" if ok else detail})

    grown = {t["team_no"]: t["members"] for t in teams}
    left = ", ".join(_person_label(u) for u in unassigned)
    add("모든 학생이 팀에 있음", not unassigned, f"팀이 없는 학생 {len(unassigned)}명이 남음({left})")
    detail, ok = _all_bad(grown, _size_problem, _size_message)
    add("팀마다 2~4명임", ok, detail)
    detail, ok = _all_bad(grown, _same_main_problem, _same_main_message)
    add("팀 안에 주 역할 중복이 없음", ok, detail)
    detail, ok = _all_bad(grown, _required_problem, _required_message)
    add("팀마다 필수 포함 역할(기획자, 웹 프로그래머)을 채움", ok, detail)
    return out


def _main_filled(members):
    """필수 포함 역할(기획자, 웹 프로그래머) 2개 가운데 어떤 팀원의 주 역할인 것의 수"""
    mains = {m["main_role"] for m in members}
    return sum(1 for role in REQUIRED_ROLES if role in mains)


def _min_square_sum(sizes, extra):
    """팀 인원 sizes에 학생 extra명을 더해 4명을 넘기지 않을 때 인원의 제곱합이 가장 작은 값. 더할 수 없으면 None

    총 인원이 같으면 제곱합이 작을수록 인원의 편차(분산)가 작음. 가장 적은 팀에 1명씩 더하면 가장 작은 값이 됨
    """
    sizes = list(sizes)
    for _ in range(extra):
        k = min(range(len(sizes)), key=lambda j: sizes[j])
        if sizes[k] >= MAX_TEAM_SIZE:
            return None
        sizes[k] += 1
    return sum(n * n for n in sizes)


def find_assignment(teams, unassigned, time_limit=5.0):
    """규칙을 지키는 배정 가운데 가장 고른 것을 찾음(되돌아가기). (pairs 또는 None, 시간 초과 여부)

    규칙을 지키는 배정(정원 4명, 팀마다 2~4명, 주 역할 중복 없음, 필수 포함 역할 충족)이 여럿이면 다음 순서로 고름
    1) 팀 인원의 편차(제곱합)가 가장 작은 것 2) 필수 포함 역할을 주 역할로 채운 수가 가장 많은 것
    3) 그래도 같으면 학번 순서와 팀 번호 순서로 탐색할 때 먼저 나오는 것. 결과가 항상 같음.
    시간 안에 끝내지 못하면 그때까지 찾은 가장 나은 배정을 돌려주고, 하나도 없으면 (None, True)
    """
    students = sorted(unassigned, key=lambda s: s["student_no"])
    team_list = sorted(teams, key=lambda t: t["team_no"])
    grown = {t["team_no"]: list(t["members"]) for t in team_list}
    deadline = time.monotonic() + time_limit
    chosen = []
    remaining_mains = [{s["main_role"] for s in students[i:]} for i in range(len(students) + 1)]
    best = {"key": None, "pairs": None}  # key = (제곱합, -주 역할로 채운 수). 작을수록 좋음

    class Timeout(Exception):
        pass

    def finished():
        for members in grown.values():
            if not MIN_TEAM_SIZE <= len(members) <= MAX_TEAM_SIZE or required_deficit(members) > 0:
                return False
        return True

    def cannot_beat(i):
        """지금까지 고른 것에서 이어 가도 best보다 나아질 수 없거나 규칙을 지킬 수 없으면 True"""
        sizes = [len(m) for m in grown.values()]
        left = len(students) - i
        if sum(max(0, MIN_TEAM_SIZE - n) for n in sizes) > left:
            return True
        for members in grown.values():
            if required_deficit(members) > MAX_TEAM_SIZE - len(members):
                return True
        if best["key"] is None:
            return False
        low = _min_square_sum(sizes, left)
        if low is None:
            return True
        fill_high = 0
        for members in grown.values():
            have = {m["main_role"] for m in members}
            filled = sum(1 for role in REQUIRED_ROLES if role in have)
            fillable = sum(1 for role in REQUIRED_ROLES if role not in have and role in remaining_mains[i])
            fill_high += filled + min(MAX_TEAM_SIZE - len(members), fillable)
        return (low, -fill_high) >= best["key"]

    def search(i):
        if time.monotonic() > deadline:
            raise Timeout
        if i == len(students):
            if finished():
                key = (sum(len(m) ** 2 for m in grown.values()), -sum(_main_filled(m) for m in grown.values()))
                if best["key"] is None or key < best["key"]:
                    best["key"], best["pairs"] = key, list(chosen)
            return
        if cannot_beat(i):
            return
        student = students[i]
        for t in team_list:
            members = grown[t["team_no"]]
            if len(members) >= MAX_TEAM_SIZE:
                continue
            if any(m["main_role"] == student["main_role"] for m in members):
                continue
            members.append(student)
            chosen.append((student["student_no"], t["team_no"]))
            search(i + 1)
            chosen.pop()
            members.pop()

    try:
        search(0)
    except Timeout:
        return (best["pairs"], False) if best["pairs"] is not None else (None, True)
    return best["pairs"], False


def explain_no_assignment(teams, unassigned):
    """규칙을 지키는 배정이 없을 때 이유 1개(PRD_step3 4.3절). 충분조건 하나를 알려 주는 진단임"""
    total = sum(len(t["members"]) for t in teams) + len(unassigned)
    if total > MAX_TEAM_SIZE * len(teams):
        return "팀 정원(4명)을 모두 합쳐도 학생 수보다 적음"
    if total < MIN_TEAM_SIZE * len(teams):
        return "학생 수가 모자라 모든 팀을 2명 이상으로 채울 수 없음"
    for t in sorted(teams, key=lambda t: t["team_no"]):
        pool = [*t["members"], *unassigned]
        for role in REQUIRED_ROLES:
            if not any(role in roles_of(s) for s in pool):
                return f"{_team_label(t['team_no'])}에 {role}를 맡을 학생이 없음"
    return "모든 경우를 따져 보았지만 규칙을 모두 지키는 배정이 없음"
