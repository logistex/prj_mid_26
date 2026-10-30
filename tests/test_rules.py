# 2026-10-30 22:40 KST
"""팀 규칙 단위 시험(PRD_step2 10.1절). DB를 쓰지 않음"""
import pytest

from mp.rules import join_violation, required_deficit, roles_of

PL, WP, FD, TT, RW, PT = "기획자", "웹 프로그래머", "프론트엔드 디자이너", "테스터", "보고서 작성자", "발표자"


def s(sid, main, *subs):
    return {"id": sid, "main_role": main, "sub_roles": list(subs)}


def test_roles_of_is_main_and_sub_union():
    assert roles_of(s(1, PL, RW, PT)) == {PL, RW, PT}


@pytest.mark.parametrize(
    "students,deficit",
    [
        ([], 2),
        ([s(1, TT)], 2),
        ([s(1, PL)], 1),  # 기획자만 있음
        ([s(1, WP)], 1),  # 웹 프로그래머만 있음
        ([s(1, PL, WP)], 1),  # 1명이 둘 다 가능해도 1개만 채움(공고 3장 표 아래 설명)
        ([s(1, PL), s(2, PL)], 1),  # 기획자 후보만 2명
        ([s(1, PL), s(2, WP)], 0),
        ([s(1, PL, WP), s(2, TT)], 1),
        ([s(1, PL, WP), s(2, WP)], 0),  # 1이 기획자, 2가 웹 프로그래머
        ([s(1, TT), s(2, PT)], 2),
    ],
)
def test_required_deficit(students, deficit):
    assert required_deficit(students) == deficit


def test_r1_full_team_is_blocked():
    members = [s(1, PL), s(2, WP), s(3, FD), s(4, TT)]
    assert join_violation(members, s(5, RW)) == "팀이 꽉 참"


def test_r2_same_main_role_is_blocked_even_if_sub_roles_differ():
    assert join_violation([s(1, PL, RW)], s(2, PL, TT)) == "같은 주 역할의 팀원이 있음"
    assert join_violation([s(1, PL, WP)], s(2, TT, PL)) is None  # 보조 역할은 중복 검사에 쓰지 않음


def test_r3_example_from_the_notice_testers_and_presenters():
    # 공고 3장 표: 테스터와 발표자만 있는 팀(2명)에 보고서 작성자가 지원하면 막힘
    assert "필수 포함 역할" in join_violation([s(1, TT), s(2, PT)], s(3, RW))


def test_r3_hard_scenario_step_11_is_blocked():
    # 부록 3(어려움) 단계 11: 팀3에 학생11(TT;PT), 학생15(PT;FD)가 있고 학생14(RW;TT)가 지원
    members = [s(11, TT, PT), s(15, PT, FD)]
    assert "필수 포함 역할" in join_violation(members, s(14, RW, TT))


def test_r3_hard_scenario_step_13_passes():
    # 부록 3(어려움) 단계 13: 팀1에 학생1(PL;RW), 학생4(WP;PL), 학생7(FD;PT;TT)이 있고 학생13(RW;PT;FD)이 지원
    members = [s(1, PL, RW), s(4, WP, PL), s(7, FD, PT, TT)]
    assert join_violation(members, s(13, RW, PT, FD)) is None


def test_empty_team_accepts_anyone():
    assert join_violation([], s(1, TT)) is None


def test_a_team_that_can_still_reach_required_roles_with_the_remaining_capacity_passes():
    # 2명(TT, PT)에 3번째 학생이 기획자: 남은 정원 1에 웹 프로그래머가 들어올 수 있음
    assert join_violation([s(1, TT), s(2, PT)], s(3, PL)) is None
