# 2026-10-30 22:30 KST
"""배정 검사 5가지와 완전 탐색 시험(PRD_step3 10.1절). DB를 쓰지 않음"""
import itertools
import random

import pytest

from conftest import DATA
from mp.roster import parse_roster
from mp.rules import check_assignment, explain_no_assignment, find_assignment, required_deficit

PL, WP, FD, TT, RW, PT = "기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자"


def st(no, main, *subs):
    return {"id": int(no), "student_no": str(no), "main_role": main, "sub_roles": list(subs)}


def team(no, *members):
    return {"team_no": no, "members": list(members)}


def good_case():
    teams = [team(1, st(1, PL)), team(2, st(2, WP))]
    unassigned = [st(3, WP), st(4, PL)]
    return teams, unassigned


def test_a_valid_assignment_passes():
    teams, unassigned = good_case()
    assert check_assignment(teams, unassigned, [("3", 1), ("4", 2)]) is None


@pytest.mark.parametrize(
    "pairs,expected",
    [
        ([("3", 1)], "검사 1번"),  # 빠진 학생
        ([("3", 1), ("4", 2), ("9", 2)], "검사 1번"),  # 모르는 학번
        ([("3", 1), ("4", 2), ("1", 2)], "검사 1번"),  # 이미 팀이 있는 학생
        ([("3", 1), ("3", 2), ("4", 2)], "검사 2번"),  # 같은 학번 2번
        ([("3", 1), ("4", 7)], "검사 2번"),  # 없는 팀 번호
    ],
)
def test_checks_1_and_2(pairs, expected):
    teams, unassigned = good_case()
    assert expected in check_assignment(teams, unassigned, pairs)


def test_check_3_team_size_too_small_and_too_large():
    teams = [team(1, st(1, PL)), team(2, st(2, WP))]
    unassigned = [st(3, TT)]
    assert "검사 3번" in check_assignment(teams, unassigned, [("3", 1)])  # 팀2는 1명
    teams = [team(1, st(1, PL), st(2, WP), st(3, TT)), team(2, st(4, FD), st(5, RW))]
    unassigned = [st(6, PT), st(7, PL)]
    assert "검사 3번" in check_assignment(teams, unassigned, [("6", 1), ("7", 1)])  # 팀1은 5명


def test_check_4_same_main_role():
    teams = [team(1, st(1, PL), st(2, WP)), team(2, st(3, TT), st(4, PL))]
    unassigned = [st(5, TT), st(6, FD)]
    assert "검사 4번" in check_assignment(teams, unassigned, [("5", 2), ("6", 1)])


def test_check_5_required_roles_must_be_actually_filled():
    # 기획자와 웹 프로그래머를 모두 맡을 수 있는 학생이 1명뿐인 팀은 필수 포함 역할을 채우지 못함
    teams = [team(1, st(1, PL, WP), st(2, TT)), team(2, st(3, PL), st(4, WP))]
    unassigned = [st(5, FD)]
    assert "검사 5번" in check_assignment(teams, unassigned, [("5", 1)])
    assert required_deficit([st(1, PL, WP), st(2, TT), st(5, FD)]) == 1


def test_find_assignment_returns_a_solution_that_passes_the_checks():
    teams, unassigned = good_case()
    pairs, timed_out = find_assignment(teams, unassigned)
    assert not timed_out
    assert check_assignment(teams, unassigned, pairs) is None


def test_find_assignment_is_deterministic():
    teams, unassigned = good_case()
    assert find_assignment(teams, unassigned) == find_assignment(teams, unassigned)


def test_find_assignment_none_and_reasons():
    # 팀2에 웹 프로그래머를 맡을 수 있는 학생이 팀원과 미배정 모두에 없음
    teams = [team(1, st(1, PL), st(2, WP)), team(2, st(3, PL), st(4, TT))]
    unassigned = [st(5, FD)]
    pairs, timed_out = find_assignment(teams, unassigned)
    assert pairs is None and not timed_out
    assert explain_no_assignment(teams, unassigned) == "팀2에 웹 프로그래머를 맡을 학생이 없음"

    # 정원이 모자람: 팀 1개에 학생 5명
    teams = [team(1, st(1, PL), st(2, WP))]
    unassigned = [st(3, TT), st(4, FD), st(5, RW)]
    assert find_assignment(teams, unassigned)[0] is None
    assert explain_no_assignment(teams, unassigned) == "팀 정원(4명)을 모두 합쳐도 학생 수보다 적음"

    # 학생 수가 모자람: 팀 3개에 학생 5명
    teams = [team(1, st(1, PL)), team(2, st(2, WP)), team(3)]
    unassigned = [st(3, TT), st(4, FD)]
    assert find_assignment(teams, unassigned)[0] is None
    assert explain_no_assignment(teams, unassigned) == "학생 수가 모자라 모든 팀을 2명 이상으로 채울 수 없음"

    # 위 어느 이유에도 해당하지 않는 경우: 주 역할 중복 때문에 배정이 없음
    teams = [team(1, st(1, PL), st(2, WP)), team(2, st(3, PL, WP), st(4, WP))]
    unassigned = [st(5, PL), st(6, PL)]
    assert find_assignment(teams, unassigned)[0] is None
    assert explain_no_assignment(teams, unassigned) == "모든 경우를 따져 보았지만 규칙을 모두 지키는 배정이 없음"


def test_find_assignment_gives_up_with_timeout_instead_of_claiming_none():
    teams = [team(n) for n in range(1, 5)]
    unassigned = [st(100 + i, [PL, WP, FD, TT, RW, PT][i % 6]) for i in range(12)]
    pairs, timed_out = find_assignment(teams, unassigned, time_limit=0.0)
    assert pairs is None and timed_out


def students_from(csv_name, base):
    out = []
    for r in parse_roster((DATA / csv_name).read_bytes()):
        out.append({"id": int(r["student_no"]), "student_no": r["student_no"], "main_role": r["main_role"], "sub_roles": r["sub_roles"]})
    return {int(s["student_no"]) - base: s for s in out}


def test_easy_scenario_state_before_step_6():
    # 부록 1 단계 5까지 끝난 뒤 마감하면 학생1~6은 팀에 있고 학생7, 8이 팀이 없는 학생이 됨
    s = students_from("쉬움.csv", 2026100)
    teams = [team(1, s[1], s[4]), team(2, s[2], s[5]), team(3, s[3], s[6])]
    pairs, timed_out = find_assignment(teams, [s[7], s[8]])
    assert not timed_out and pairs is not None
    assert check_assignment(teams, [s[7], s[8]], pairs) is None


def test_middle_scenario_state_before_step_11():
    # 부록 2 단계 9 뒤: 팀1(학생1, 5), 팀2(학생6, 9), 팀3과 팀4는 빈 팀. 학생2, 3, 4, 7, 8, 10, 11, 12가 팀이 없음
    s = students_from("중간.csv", 2026200)
    teams = [team(1, s[1], s[5]), team(2, s[6], s[9]), team(3), team(4)]
    unassigned = [s[i] for i in (2, 3, 4, 7, 8, 10, 11, 12)]
    pairs, timed_out = find_assignment(teams, unassigned)
    assert not timed_out and pairs is not None
    assert check_assignment(teams, unassigned, pairs) is None


def test_hard_scenario_state_before_step_15():
    # 부록 3 단계 14 뒤: 팀1(학생1, 4, 7), 팀2(학생2, 8, 5), 팀3(학생11, 15), 팀4는 빈 팀
    s = students_from("어려움.csv", 2026300)
    teams = [team(1, s[1], s[4], s[7]), team(2, s[2], s[8], s[5]), team(3, s[11], s[15]), team(4)]
    unassigned = [s[i] for i in (3, 6, 9, 10, 12, 13, 14, 16)]
    pairs, timed_out = find_assignment(teams, unassigned)
    assert not timed_out and pairs is not None
    assert check_assignment(teams, unassigned, pairs) is None


# ---- 앱이 직접 배정할 때 고르는 순서(규칙을 지킨 배정 가운데 인원 편차, 주 역할 충족, 탐색 순서) ----

def sizes_after(teams, pairs):
    grown = {t["team_no"]: len(t["members"]) for t in teams}
    for _, team_no in pairs:
        grown[team_no] += 1
    return [grown[n] for n in sorted(grown)]


def brute_best(teams, unassigned):
    """모든 배정을 따져 규칙을 지키는 것 가운데 (인원 제곱합, -주 역할 충족)이 가장 작은 첫 배정"""
    team_nos = sorted(t["team_no"] for t in teams)
    students = sorted(unassigned, key=lambda s: s["student_no"])
    best = None
    for combo in itertools.product(team_nos, repeat=len(students)):
        pairs = [(s["student_no"], n) for s, n in zip(students, combo)]
        if check_assignment(teams, unassigned, pairs) is not None:
            continue
        grown = {t["team_no"]: list(t["members"]) for t in teams}
        for s, n in zip(students, combo):
            grown[n].append(s)
        key = (sum(len(m) ** 2 for m in grown.values()),
               -sum(sum(1 for r in (PL, WP) if r in {x["main_role"] for x in m}) for m in grown.values()))
        if best is None or key < best[0]:
            best = (key, pairs)
    return None if best is None else best[1]


def test_find_assignment_spreads_students_instead_of_filling_early_teams():
    # 처음 찾은 배정은 두 학생을 모두 팀1에 넣어 인원이 4, 2, 2가 됨. 가장 고른 배정은 3, 3, 2임
    s = students_from("쉬움.csv", 2026100)
    teams = [team(1, s[1], s[4]), team(2, s[2], s[5]), team(3, s[3], s[6])]
    pairs, _ = find_assignment(teams, [s[7], s[8]])
    assert sizes_after(teams, pairs) == [3, 3, 2]
    assert pairs == [("2026107", 1), ("2026108", 2)]


def test_find_assignment_prefers_main_role_over_sub_role_when_spread_is_equal():
    # 두 배정 모두 인원이 3, 2임. 탐색 순서로는 학생4(웹이 보조)가 팀2에 가지만, 웹이 주 역할인 학생3을 팀2에 넣는 쪽을 고름
    teams = [team(1, st(1, PL), st(2, WP)), team(2, st(5, PL))]
    unassigned = [st(3, WP), st(4, FD, WP)]
    pairs, _ = find_assignment(teams, unassigned)
    assert sizes_after(teams, pairs) == [3, 2]
    assert pairs == [("3", 2), ("4", 1)]


def test_find_assignment_keeps_first_in_order_when_everything_else_is_equal():
    teams = [team(1, st(1, PL)), team(2, st(2, PL))]
    unassigned = [st(3, WP), st(4, WP)]
    assert find_assignment(teams, unassigned)[0] == [("3", 1), ("4", 2)]


@pytest.mark.parametrize(
    "csv_name,base,members,loose",
    [
        ("쉬움.csv", 2026100, {1: (1, 4), 2: (2, 5), 3: (3, 6)}, (7, 8)),
        ("중간.csv", 2026200, {1: (1, 5), 2: (6, 9), 3: (), 4: ()}, (2, 3, 4, 7, 8, 10, 11, 12)),
        ("어려움.csv", 2026300, {1: (1, 4, 7), 2: (2, 8, 5), 3: (11, 15), 4: ()}, (3, 6, 9, 10, 12, 13, 14, 16)),
    ],
)
def test_find_assignment_in_the_three_scenario_closing_states_is_valid_and_the_most_even(csv_name, base, members, loose):
    s = students_from(csv_name, base)
    teams = [team(n, *[s[i] for i in ids]) for n, ids in members.items()]
    unassigned = [s[i] for i in loose]
    pairs, timed_out = find_assignment(teams, unassigned)
    assert not timed_out and check_assignment(teams, unassigned, pairs) is None
    assert pairs == brute_best(teams, unassigned)  # 모든 배정을 따져 얻은 가장 고른 첫 배정과 같음
    total = sum(len(t["members"]) for t in teams) + len(unassigned)
    sizes = sizes_after(teams, pairs)
    assert max(sizes) - min(sizes) <= (0 if total % len(teams) == 0 else 1) or csv_name == "어려움.csv"


def test_find_assignment_equals_brute_force_on_random_cases():
    rng = random.Random(5)
    roles = [PL, WP, FD, TT, RW, PT]
    solved = 0
    for _ in range(120):
        team_nos = range(1, rng.randint(2, 4) + 1)
        nid = 1
        teams = []
        for n in team_nos:
            mains = rng.sample(roles, rng.randint(0, 2))
            members = []
            for m in mains:
                members.append(st(nid, m, *[r for r in rng.sample(roles, rng.randint(0, 2)) if r != m]))
                nid += 1
            teams.append(team(n, *members))
        unassigned = []
        for _ in range(rng.randint(2, 7)):
            m = rng.choice(roles)
            unassigned.append(st(nid, m, *[r for r in rng.sample(roles, 2) if r != m]))
            nid += 1
        expected = brute_best(teams, unassigned)
        pairs, timed_out = find_assignment(teams, unassigned)
        assert not timed_out
        assert pairs == expected
        solved += expected is not None
    assert solved >= 25  # 해가 있는 사례가 충분히 섞여 있어야 비교가 뜻을 가짐
