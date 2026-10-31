# 2026-10-30 22:40 KST
"""팀 규칙. DB를 만지지 않는 순수 함수(PRD_step2 3장). 학생은 {id, main_role, sub_roles}를 가진 dict임"""
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

    if assigned - wanted:
        detail = "팀이 없는 학생이 아닌 학번이 들어 있음"
    else:
        detail = "배정되지 않은 학생이 있음"
    add("팀이 없는 학생이 빠짐없이 배정되고, 그 밖의 학번은 없음", assigned == wanted, detail)
    dup = [no for no, c in counts.items() if c > 1]
    bad_team = sorted({team_no for _, team_no in pairs if team_no not in team_nos})
    add("한 학생이 1번만 배정되고 팀 번호가 있는 팀임", not dup and not bad_team,
        "한 학생이 두 번 이상 배정됨" if dup else "없는 팀 번호가 들어 있음")

    grown = {t["team_no"]: list(t["members"]) for t in teams}
    placed = set()
    for student_no, team_no in pairs:  # 앞의 2가지를 어긴 배정은 5가지를 따로 보여 주기 위해 올바른 쌍만 얹음
        if student_no in by_no and team_no in grown and student_no not in placed:
            placed.add(student_no)
            grown[team_no].append(by_no[student_no])

    def first_bad(test, message):
        for team_no in sorted(grown):
            problem = test(grown[team_no])
            if problem is not None:
                return message(team_no, problem), False
        return "", True

    detail, ok = first_bad(lambda m: None if MIN_TEAM_SIZE <= len(m) <= MAX_TEAM_SIZE else len(m),
                           lambda n, k: f"{_team_label(n)}의 인원이 {k}명임(2~4명이어야 함)")
    add("배정한 뒤 모든 팀이 2~4명임", ok, detail)
    detail, ok = first_bad(lambda m: True if len({x["main_role"] for x in m}) != len(m) else None,
                           lambda n, _: f"{_team_label(n)}에 주 역할이 같은 학생이 있음")
    add("팀 안에 주 역할이 같은 학생이 없음", ok, detail)
    detail, ok = first_bad(lambda m: True if required_deficit(m) > 0 else None,
                           lambda n, _: f"{_team_label(n)}에 필수 포함 역할(기획자, 웹 프로그래머)을 채울 수 없음")
    add("모든 팀이 필수 포함 역할(기획자, 웹 프로그래머)을 채울 수 있음", ok, detail)
    return out


def final_state_checks(teams, unassigned):
    """확정한 팀 구성의 규칙 확인 4가지(PRD_step4 3.4절). [{no, title, ok, detail}] 4개

    teams: [{team_no, members:[학생 dict]}], unassigned: 팀이 없는 학생 목록
    """
    out = []

    def add(title, ok, detail):
        out.append({"no": len(out) + 1, "title": title, "ok": ok, "detail": "통과" if ok else detail})

    def first_bad(test, message):
        for t in sorted(teams, key=lambda t: t["team_no"]):
            problem = test(t["members"])
            if problem is not None:
                return message(t["team_no"], problem), False
        return "", True

    add("모든 학생이 팀에 있음", not unassigned, f"팀이 없는 학생이 {len(unassigned)}명 남음")
    detail, ok = first_bad(lambda m: None if MIN_TEAM_SIZE <= len(m) <= MAX_TEAM_SIZE else len(m),
                           lambda n, k: f"{_team_label(n)}의 인원이 {k}명임(2~4명이어야 함)")
    add("팀마다 2~4명임", ok, detail)
    detail, ok = first_bad(lambda m: True if len({x["main_role"] for x in m}) != len(m) else None,
                           lambda n, _: f"{_team_label(n)}에 주 역할이 같은 학생이 있음")
    add("팀 안에 주 역할 중복이 없음", ok, detail)
    detail, ok = first_bad(lambda m: True if required_deficit(m) > 0 else None,
                           lambda n, _: f"{_team_label(n)}에 필수 포함 역할(기획자, 웹 프로그래머)을 채울 수 없음")
    add("팀마다 필수 포함 역할(기획자, 웹 프로그래머)을 채움", ok, detail)
    return out


def find_assignment(teams, unassigned, time_limit=5.0):
    """규칙을 지키는 배정을 모든 경우를 따져 찾음(되돌아가기). (pairs 또는 None, 시간 초과 여부)

    학번 순서와 팀 번호 순서로 탐색하므로 결과가 항상 같음. 정원 초과(R1)와 주 역할 중복(R2)이 생기는 가지는 자름
    """
    students = sorted(unassigned, key=lambda s: s["student_no"])
    team_list = sorted(teams, key=lambda t: t["team_no"])
    grown = {t["team_no"]: list(t["members"]) for t in team_list}
    deadline = time.monotonic() + time_limit
    chosen = []

    class Timeout(Exception):
        pass

    def finished():
        for team_no, members in grown.items():
            if not MIN_TEAM_SIZE <= len(members) <= MAX_TEAM_SIZE or required_deficit(members) > 0:
                return False
        return True

    def search(i):
        if time.monotonic() > deadline:
            raise Timeout
        if i == len(students):
            return finished()
        student = students[i]
        for t in team_list:
            members = grown[t["team_no"]]
            if len(members) >= MAX_TEAM_SIZE:
                continue
            if any(m["main_role"] == student["main_role"] for m in members):
                continue
            members.append(student)
            chosen.append((student["student_no"], t["team_no"]))
            if search(i + 1):
                return True
            chosen.pop()
            members.pop()
        return False

    try:
        found = search(0)
    except Timeout:
        return None, True
    return (list(chosen) if found else None), False


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
