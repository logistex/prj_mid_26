# 2026-11-01 12:40 KST
"""시나리오 실행 탭의 시간 줄, 상황 설명, 이전과 이후를 겹친 판(PRD_step4 4.2절)의 순수 시험. DB와 네트워크를 쓰지 않음"""
import re

import pytest

from mp import practice, practice_board

HEADER = "step,action,actor,team_no,target,choice,expected,note\n"


def units_of(text):
    return practice.split_units(practice.parse_steps(("﻿" + HEADER + text).encode("utf-8")))


def person(n, main="기획자", subs=()):
    return {"id": 100 + n, "student_no": f"s{n}", "name": f"학생{n}", "main_role": main, "sub_roles": list(subs)}


def pend(n, votes=None):
    d = person(n)
    d["votes"] = votes or {}
    return d


def view(teams, unassigned=(), phase="open"):
    return {"phase": phase, "unassigned": list(unassigned),
            "teams": [{"id": no, "team_no": no, "name": f"팀{no}", "members": list(m), "pending": list(p)}
                      for no, m, p in teams]}


def rr(action, actor, status, message="", skipped=False):
    return {"action": action, "actor": actor, "status": status, "message": message, "skipped": skipped}


def name_of(no):
    return {f"s{i}": f"학생{i}" for i in range(1, 20)}.get(no, no)


# 학생7이 팀1에 지원하고 팀원 학생1과 학생4가 찬성과 거부를 해 거절된 단계
REJECT_TEXT = "1,지원,s7,1,,,대기,\n1,투표,s1,,s7,찬성,대기,\n1,투표,s4,,s7,거부,거절,\n"


def reject_record():
    team1 = [person(1), person(4, "웹 프로그래머")]
    v = view([(1, team1, []), (2, [], [])], unassigned=[person(7, "프론트엔드 디자이너")])
    return {"rows": [rr("지원", "s7", "대기"), rr("투표", "s1", "대기"), rr("투표", "s4", "거절")],
            "before": v, "after": v, "after_db": v}


# ---- 이름 뒤의 조사 ----

@pytest.mark.parametrize("text,expected", [("학생7", "학생7이"), ("학생4", "학생4가"), ("학생1", "학생1이"), ("학생2", "학생2가"),
                                           ("학생0", "학생0이"), ("학생9", "학생9가"), ("김철수", "김철수가"), ("이영", "이영이")])
def test_subject_particle_follows_the_last_syllable(text, expected):
    assert practice.subject(text) == expected


def test_topic_particle_and_unknown_endings():
    assert practice.topic("팀1") == "팀1은" and practice.topic("학생5") == "학생5는"
    assert practice.subject("Amy") == "Amy이(가)"


# ---- 시간 줄의 한 줄 요약과 결과 ----

def test_one_line_summary_of_applications_and_votes():
    (unit,) = units_of(REJECT_TEXT)
    assert practice.summarize_unit(unit, name_of) == "학생7이 팀1에 지원, 학생1 찬성, 학생4 거부"


def test_a_vote_on_an_application_from_an_earlier_step_names_the_applicant():
    (unit,) = units_of("1,투표,s2,,s9,찬성,승인,\n")
    assert practice.summarize_unit(unit, name_of) == "학생2가 학생9에 찬성"


def test_admin_units_have_fixed_summaries():
    close, assign, confirm = units_of("1,마감,,,,,,\n2,배정,,,,,,\n3,확정,,,,,,\n")
    assert [practice.summarize_unit(u, name_of) for u in (close, assign, confirm)] == ["모집 마감", "AI 배정", "배정 확정"]


def test_unit_result_is_the_last_actual_status_that_was_not_skipped():
    (unit,) = units_of(REJECT_TEXT)
    assert practice.unit_result(unit, reject_record()) == "거절"
    skipped = {"rows": [rr("지원", "s7", "막힘"), rr("투표", "s1", "건너뜀", skipped=True)]}
    assert practice.unit_result(unit, skipped) == "막힘"
    assert practice.unit_result(unit, {"rows": [rr("투표", "s1", "건너뜀", skipped=True)]}) == "건너뜀"


# ---- 그 단계에서 일어난 일 ----

def test_narration_of_a_rejected_application_follows_the_actual_votes():
    (unit,) = units_of(REJECT_TEXT)
    assert practice.narrate(unit, reject_record(), name_of) == (
        "학생7이 팀1에 지원함 → 팀원 2명의 투표를 기다림 → 학생1 찬성, 학생4 거부 → "
        "거절. 팀1은 그대로이고 학생7은 팀이 없는 학생으로 돌아감")


def test_narration_of_an_approved_application():
    (unit,) = units_of("1,지원,s4,1,,,대기,\n1,투표,s1,,s4,찬성,승인,\n")
    before = view([(1, [person(1)], []), (2, [], [])], unassigned=[person(4)])
    after = view([(1, [person(1), person(4)], []), (2, [], [])])
    record = {"rows": [rr("지원", "s4", "대기"), rr("투표", "s1", "승인")], "before": before, "after": after}
    assert practice.narrate(unit, record, name_of) == (
        "학생4가 팀1에 지원함 → 팀원 1명의 투표를 기다림 → 학생1 찬성 → 승인. 학생4가 팀1의 팀원이 됨")


def test_narration_of_a_blocked_application_and_an_immediate_approval():
    (unit,) = units_of("1,지원,s3,2,,,막힘,\n1,투표,s1,,s3,찬성,,\n")
    v = view([(2, [], [])], unassigned=[person(3)])
    record = {"rows": [rr("지원", "s3", "막힘", "팀이 가득 참"), rr("투표", "s1", "건너뜀", skipped=True)], "before": v, "after": v}
    assert practice.narrate(unit, record, name_of) == "학생3이 팀2에 지원함 → 막힘: 팀이 가득 참"
    (unit2,) = units_of("1,지원,s2,2,,,승인,\n")
    after = view([(2, [person(2)], [])])
    record2 = {"rows": [rr("지원", "s2", "승인")], "before": view([(2, [], [])], unassigned=[person(2)]), "after": after}
    assert practice.narrate(unit2, record2, name_of) == "학생2가 팀2에 지원함 → 바로 승인되어 팀원이 됨"


def test_narration_of_admin_units_uses_the_message_of_the_service():
    (unit,) = units_of("1,마감,,,,,승인,\n")
    v = view([(1, [], [])])
    record = {"rows": [rr("마감", "", "승인", "모집을 마감함. 대기 지원 1건을 거절함")], "before": v, "after": v}
    assert practice.narrate(unit, record, name_of) == "모집 마감 → 승인: 모집을 마감함. 대기 지원 1건을 거절함"


# ---- 진행과 시나리오 이름 ----

def test_progress_counts_steps_whose_units_are_all_done():
    units = units_of("1,지원,a,1,,,,\n2,지원,b,1,,,,\n3,마감,,,,,,\n3,배정,,,,,,\n3,확정,,,,,,\n4,지원,c,1,,,,\n")
    states = practice.unit_states(units, {u.label: {"rows": []} for u in units[:3]})
    p = practice.progress(units, states)
    assert (p.total, p.done, p.partial) == (4, 2, 3)
    assert practice.progress_text(p) == "4단계 가운데 2단계까지 실행함(3단계는 일부만 실행함)"
    done = practice.progress(units, ["실행함"] * 6)
    assert practice.progress_text(done) == "4단계 가운데 4단계까지 실행함"
    assert practice.progress_text(practice.progress(units, ["다음 차례"] + ["대기"] * 5)) == "4단계 가운데 0단계까지 실행함"


@pytest.mark.parametrize("name,title", [("쉬움_단계.csv", "쉬움 시나리오"), ("중간 단계.CSV", "중간 시나리오"),
                                        ("C:\\a\\b\\어려움-단계.csv", "어려움 시나리오"), ("steps.csv", "steps 시나리오"),
                                        (None, "시나리오"), ("", "시나리오")])
def test_scenario_title_comes_from_the_uploaded_file_name(name, title):
    assert practice.scenario_title(name) == title


# ---- 이전과 이후를 겹친 판 ----

def board_of(unit, record):
    return practice_board.build_board(record["before"], record["after"], unit.rows, record["rows"])


def team(model, no):
    return next(t for t in model["teams"] if t["team_no"] == no)


def test_a_rejected_application_is_struck_through_with_each_members_vote():
    (unit,) = units_of(REJECT_TEXT)
    model = board_of(unit, reject_record())
    t1 = team(model, 1)
    (app,) = t1["apps"]
    assert app["state"] == "rejected" and app["name"] == "학생7"
    assert app["votes"] == [("학생1", "찬성"), ("학생4", "거부")]
    assert t1["changed"] and not team(model, 2)["changed"]
    html = practice_board.board_html(model)
    assert "<s>학생7</s>" in html and "거절된 지원" in html
    assert "학생1 ○" in html and "학생4 ✕" in html


def test_a_pending_application_shows_votes_not_cast_yet_and_new_members_and_empty_slots():
    members = [person(1), person(4)]
    before = view([(1, members, [])], unassigned=[person(7), person(8)])
    after = view([(1, members + [person(8)], [pend(7, {101: "찬성"})])], unassigned=[person(7)])
    (unit,) = units_of("1,지원,s7,1,,,대기,\n1,투표,s1,,s7,찬성,대기,\n")
    record = {"rows": [rr("지원", "s7", "대기"), rr("투표", "s1", "대기")], "before": before, "after": after}
    model = board_of(unit, record)
    t1 = team(model, 1)
    assert [s["state"] for s in t1["slots"]] == ["same", "same", "new", "empty"]
    (app,) = t1["apps"]
    assert app["state"] == "pending" and app["new"] is True
    assert app["votes"] == [("학생1", "찬성"), ("학생4", None), ("학생8", None)]
    html = practice_board.board_html(model)
    assert "pb-pending" in html and "학생4 ?" in html and "빈 자리" in html and "3/4" in html


def test_removed_members_are_struck_through_and_their_students_appear_in_the_unassigned_line_in_green():
    before = view([(1, [person(1), person(2), person(3)], [])])
    after = view([(1, [person(1)], [])], unassigned=[person(2), person(3)])
    model = practice_board.build_board(before, after, (), [])
    t1 = team(model, 1)
    assert [s["state"] for s in t1["slots"]] == ["same", "gone", "gone", "empty"]
    assert [u["state"] for u in model["unassigned"]] == ["new", "new"]
    html = practice_board.board_html(model)
    assert html.count("<s>") == 2 and "pb-new" in html and "−" in html and "+" in html


def test_students_who_joined_a_team_leave_the_unassigned_line_struck_through():
    before = view([(1, [person(1)], [])], unassigned=[person(5)])
    after = view([(1, [person(1), person(5)], [])])
    model = practice_board.build_board(before, after, (), [])
    assert [u["state"] for u in model["unassigned"]] == ["gone"]
    assert "<s>학생5</s>" in practice_board.board_html(model)


def test_a_pending_application_that_closed_with_the_recruitment_shows_as_rejected_with_its_votes():
    members = [person(1), person(2)]
    before = view([(1, members, [pend(7, {101: "찬성"})])], unassigned=[person(7)])
    after = view([(1, members, [])], unassigned=[person(7)], phase="closed")
    model = practice_board.build_board(before, after, (), [])
    (app,) = team(model, 1)["apps"]
    assert app["state"] == "rejected" and app["votes"] == [("학생1", "찬성"), ("학생2", None)]


def test_a_blocked_application_is_shown_as_blocked_on_its_team():
    (unit,) = units_of("1,지원,s3,2,,,막힘,\n")
    v = view([(1, [], []), (2, [person(1)], [])], unassigned=[person(3)])
    record = {"rows": [rr("지원", "s3", "막힘", "팀이 가득 참")], "before": v, "after": v}
    model = board_of(unit, record)
    (app,) = team(model, 2)["apps"]
    assert app["state"] == "blocked" and team(model, 2)["changed"]
    assert "지원 막힘" in practice_board.board_html(model)


def test_nothing_changed_means_no_card_is_marked_and_the_state_board_marks_nothing():
    v = view([(1, [person(1)], [pend(5, {})]), (2, [], [])], unassigned=[person(5)])
    model = practice_board.state_board(v)
    assert not any(t["changed"] for t in model["teams"])
    assert "pb-changed" not in practice_board.board_html(model)


def test_a_proposed_assignment_is_marked_as_proposed():
    before = view([(1, [person(1)], [])], unassigned=[person(5)])
    proposed = person(5)
    proposed["proposed"] = True
    after = view([(1, [person(1), proposed], [])])
    model = practice_board.build_board(before, after, (), [])
    assert [s["state"] for s in team(model, 1)["slots"]][:2] == ["same", "proposed"]
    assert "배정안" in practice_board.board_html(model)


def test_names_are_escaped_in_the_html():
    bad = person(1)
    bad["name"] = "<script>alert(1)</script>"
    html = practice_board.board_html(practice_board.state_board(view([(1, [bad], [])])))
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_every_team_card_has_four_slots_and_no_symbol_is_color_only():
    v = view([(1, [person(1), person(2), person(3), person(4)], []), (2, [], [])])
    html = practice_board.board_html(practice_board.state_board(v))
    cards = re.findall(r'<section class="pb-card.*?</section>', html, flags=re.S)
    assert len(cards) == 2 and all(c.count('class="pb-slot ') == 4 for c in cards)
    assert "4/4" in html and "0/4" in html


# ---- 이름 끝의 괄호 ----

@pytest.mark.parametrize("name,short", [("학생7(FD;PT)", "학생7"), ("학생1(PL;RW) ", "학생1"), ("학생2", "학생2"), ("김철수(팀장)", "김철수"),
                                        ("(PL)", "(PL)")])
def test_short_name_drops_the_trailing_parenthesis_of_the_roster_name(name, short):
    assert practice.short_name(name) == short


def test_the_board_uses_short_names_and_keeps_the_roles_beside_them():
    p = person(7, "프론트엔드 디자이너", ("발표자",))
    p["name"] = "학생7(FD;PT)"
    model = practice_board.state_board(view([(1, [p], [])]))
    slot = team(model, 1)["slots"][0]
    assert slot["name"] == "학생7" and slot["role"] == "프론트엔드 디자이너 (보조: 발표자)"


# ---- 일어난 일 문장의 결함 2개(재현 시험): 같은 학생의 지원 2번, 거절된 까닭 ----

def two_applications_record():
    team4 = [person(1)]
    before = view([(3, [], []), (4, team4, [])], unassigned=[person(12)])
    after = view([(3, [], []), (4, team4, [pend(12)])], unassigned=[person(12)])
    rows = [rr("지원", "s12", "대기", "투표를 기다림"), rr("지원", "s12", "막힘", "결과를 기다리는 지원이 있음")]
    return {"rows": rows, "before": before, "after": after, "after_db": after}


def test_two_applications_by_the_same_student_in_one_step_are_both_in_the_narration():
    (unit,) = units_of("1,지원,s12,4,,,대기,\n1,지원,s12,3,,,막힘,\n")
    assert practice.narrate(unit, two_applications_record(), name_of) == (
        "학생12가 팀4에 지원함 → 팀원 1명의 투표를 기다림 / "
        "학생12가 팀3에 지원함 → 막힘: 결과를 기다리는 지원이 있음")


def test_each_application_of_the_same_student_is_its_own_outcome_and_a_later_vote_goes_to_the_open_one():
    (unit,) = units_of("1,지원,s12,4,,,대기,\n1,지원,s12,3,,,막힘,\n1,투표,s1,,s12,찬성,승인,\n")
    rows = [rr("지원", "s12", "대기"), rr("지원", "s12", "막힘", "결과를 기다리는 지원이 있음"), rr("투표", "s1", "승인")]
    first, second = practice.application_outcomes(unit.rows, rows)
    assert (first.team_no, first.status, first.votes) == (4, "승인", [("s1", "찬성")])
    assert (second.team_no, second.status, second.votes) == (3, "막힘", [])


def test_the_board_shows_both_the_pending_application_and_the_blocked_one_with_its_reason():
    (unit,) = units_of("1,지원,s12,4,,,대기,\n1,지원,s12,3,,,막힘,\n")
    model = board_of(unit, two_applications_record())
    assert [a["state"] for a in team(model, 4)["apps"]] == ["pending"]
    (blocked,) = team(model, 3)["apps"]
    assert blocked["state"] == "blocked" and blocked["reason"] == "결과를 기다리는 지원이 있음"
    assert "지원 막힘" in practice_board.board_html(model) and "결과를 기다리는 지원이 있음" in practice_board.board_html(model)


def rejected_by_check_record():
    members = [person(2), person(8), person(5)]
    before = view([(2, members, [pend(6, {102: "찬성", 108: "찬성"})])], unassigned=[person(6)])
    after = view([(2, members, [])], unassigned=[person(6)])
    reason = "승인 직전 검사: 같은 주 역할의 팀원이 있음"
    rows = [rr("투표", "s2", "대기"), rr("투표", "s8", "대기"), rr("투표", "s5", "거절", reason)]
    return {"rows": rows, "before": before, "after": after, "after_db": after}


REJECTED_BY_CHECK = "1,투표,s2,,s6,찬성,대기,\n1,투표,s8,,s6,찬성,대기,\n1,투표,s5,,s6,찬성,거절,\n"


def test_a_rejection_names_the_reason_from_the_record_and_the_members_voted_on_the_application():
    (unit,) = units_of(REJECTED_BY_CHECK)
    assert practice.narrate(unit, rejected_by_check_record(), name_of) == (
        "팀원들이 학생6의 팀2 지원에 투표함 → 학생2 찬성, 학생8 찬성, 학생5 찬성 → "
        "거절(까닭: 승인 직전 검사: 같은 주 역할의 팀원이 있음). 팀2는 그대로이고 학생6은 팀이 없는 학생으로 돌아감")


def test_a_rejection_by_a_members_refusal_names_that_reason_too():
    (unit,) = units_of(REJECT_TEXT)
    record = reject_record()
    record["rows"][2]["message"] = "팀원이 거부함"
    assert practice.narrate(unit, record, name_of) == (
        "학생7이 팀1에 지원함 → 팀원 2명의 투표를 기다림 → 학생1 찬성, 학생4 거부 → "
        "거절(까닭: 팀원이 거부함). 팀1은 그대로이고 학생7은 팀이 없는 학생으로 돌아감")


def test_the_rejected_application_card_shows_the_reason():
    (unit,) = units_of(REJECTED_BY_CHECK)
    model = board_of(unit, rejected_by_check_record())
    (app,) = team(model, 2)["apps"]
    assert app["state"] == "rejected" and app["reason"] == "승인 직전 검사: 같은 주 역할의 팀원이 있음"
    assert "까닭: 승인 직전 검사: 같은 주 역할의 팀원이 있음" in practice_board.board_html(model)


def test_a_rejection_made_by_closing_the_recruitment_says_so_on_the_card():
    members = [person(1), person(2)]
    before = view([(1, members, [pend(7, {101: "찬성"})])], unassigned=[person(7)])
    after = view([(1, members, [])], unassigned=[person(7)], phase="closed")
    (app,) = team(practice_board.build_board(before, after, (), []), 1)["apps"]
    assert app["reason"] == "모집을 마감함"


# ---- 팀 카드의 필수 포함 역할 줄과 전체 줄(요청 6번) ----

PL, WP = "기획자", "웹 프로그래머"


def need_line(html, team_name):
    """team_name 카드의 필수 포함 역할 줄(태그를 뗀 글)"""
    card = html.split('<section class="pb-card')[[f"<b>{team_name}</b>" in c for c in html.split('<section class="pb-card')].index(True)]
    line = re.search(r'<div class="pb-need">(.*?)</div>', card).group(1)
    return re.sub(r"<[^>]+>", "", line)


def total_line(html):
    return re.sub(r"<[^>]+>", "", re.search(r'<p class="pb-total">(.*?)</p>', html).group(1))


def test_the_team_line_names_who_fills_each_required_role_and_marks_a_sub_role_as_sub():
    v = view([(1, [person(1, PL), person(4, WP)], []),
              (2, [person(2, "테스터", [PL]), person(5, WP)], [])])
    html = practice_board.board_html(practice_board.state_board(v))
    assert need_line(html, "팀1") == "기획자 ○ 학생1 · 웹 프로그래머 ○ 학생4 · 주 역할 중복 없음 ○"
    assert need_line(html, "팀2") == "기획자 ○ 학생2(보조) · 웹 프로그래머 ○ 학생5 · 주 역할 중복 없음 ○"


def test_one_student_who_can_do_both_required_roles_fills_only_one_of_them():
    v = view([(1, [person(1, PL, [WP]), person(2, "테스터")], [])])
    line = need_line(practice_board.board_html(practice_board.state_board(v)), "팀1")
    assert line.startswith("기획자 ○ 학생1 · 웹 프로그래머 필요 ·")


def test_an_empty_required_role_says_need_before_the_confirmation_and_a_red_cross_after_it():
    open_view = view([(1, [person(1, PL)], [])])
    html = practice_board.board_html(practice_board.state_board(open_view))
    assert "웹 프로그래머 필요" in need_line(html, "팀1") and "✕" not in need_line(html, "팀1")
    assert '<span class="pb-none">필요</span>' in html
    done = view([(1, [person(1, PL)], [])], phase="confirmed")
    html = practice_board.board_html(practice_board.state_board(done))
    assert "웹 프로그래머 ✕" in need_line(html, "팀1") and "필요" not in need_line(html, "팀1")
    assert '<span class="pb-no">✕</span>' in html


def test_a_duplicate_main_role_is_marked_with_the_students_in_red():
    v = view([(1, [person(1, PL), person(2, PL), person(3, WP)], [])])
    line = need_line(practice_board.board_html(practice_board.state_board(v)), "팀1")
    assert "주 역할 중복 ✕ 기획자(학생1, 학생2)" in line


def test_the_total_line_is_above_the_cards_and_counts_what_is_left_before_the_confirmation():
    v = view([(1, [person(1, PL), person(4, WP)], []), (2, [person(2, PL)], [])], unassigned=[person(9, "테스터")])
    html = practice_board.board_html(practice_board.state_board(v))
    assert html.index("pb-total") < html.index("pb-grid")
    assert total_line(html) == "전체: 팀이 없는 학생 1명 · 인원 2~4명 남음(1팀) · 주 역할 중복 없음 ○ · 필수 포함 역할 남음(1팀)"
    ok = view([(1, [person(1, PL), person(4, WP)], []), (2, [person(2, PL), person(5, WP)], [])])
    assert total_line(practice_board.board_html(practice_board.state_board(ok))) == (
        "전체: 팀이 없는 학생 0명 · 인원 2~4명 ○ · 주 역할 중복 없음 ○ · 필수 포함 역할 ○")


def test_the_total_line_uses_a_red_cross_with_the_count_after_the_confirmation():
    v = view([(1, [person(1, PL), person(4, WP)], []), (2, [person(2, PL)], [])], phase="confirmed")
    html = practice_board.board_html(practice_board.state_board(v))
    assert total_line(html) == "전체: 팀이 없는 학생 0명 · 인원 2~4명 ✕(1팀) · 주 역할 중복 없음 ○ · 필수 포함 역할 ✕(1팀)"
    assert "남음" not in total_line(html)


def test_the_status_marks_are_plain_text_with_symbols_not_boxes():
    html = practice_board.board_html(practice_board.state_board(view([(1, [person(1, PL)], [])])))
    assert "○" in html and "필요" in html
    from mp import style
    for cls in ("pb-flag", "pb-tag", "pv-result"):
        rule = re.search(r"\n\s*\.%s\s*\{([^}]*)\}" % cls, style.PRACTICE_CSS)
        assert rule and not re.search(r"border|background|box-shadow", rule.group(1)), cls  # 상황 표시는 테두리, 바탕, 그림자가 없음


# ---- 모델을 몇 번 불렀고 누가 배정했는지(요청 2번) ----

@pytest.mark.parametrize("part,text", [
    ({"calls_models": False, "called": 0, "source": "앱이 직접 배정"}, "AI 안 부름 · 앱이 직접 배정"),
    ({"calls_models": True, "called": 1, "source": "1차 모델(a:free)"}, "AI 1번 부름 · 1차 모델의 배정안"),
    ({"calls_models": True, "called": 2, "source": "2차 모델(b:free)"}, "AI 2번 부름 · 2차 모델의 배정안"),
    ({"calls_models": True, "called": 3, "source": "앱이 직접 배정"}, "AI 3번 부름 · 모두 실패해 앱이 직접 배정"),
    ({"calls_models": True, "called": 0, "source": None}, "AI 안 부름 · 배정안 없음"),
    ({"calls_models": False, "called": 0, "source": None}, "AI 안 부름 · 배정안 없음"),
])
def test_ai_source_text_says_how_many_times_and_who_assigned(part, text):
    assert practice.ai_source_text(part) == text


def assign_unit():
    return units_of("1,마감,,,,,승인,\n1,배정,,,,,승인,\n")[1]


def test_the_sentence_says_no_ai_was_called_when_the_real_model_call_was_off():
    v = view([(1, [person(1)], [])])
    rec = {"rows": [rr("배정", "", "승인", "배정안을 만듦(앱이 직접 배정)")], "before": v, "after": v, "after_db": v,
           "ai": {"calls_models": False, "called": 0, "source": "앱이 직접 배정"}}
    text = practice.narrate(assign_unit(), rec, name_of)
    assert text == ("AI 배정 → 승인: 배정안을 만듦(앱이 직접 배정). AI를 부르지 않음(실제 AI 모델 호출을 껐음). "
                    "앱이 규칙에 맞는 배정을 직접 찾음")
    rec["ai"] = {"calls_models": True, "called": 1, "source": "1차 모델(a:free)"}
    assert "AI를 부르지 않음" not in practice.narrate(assign_unit(), rec, name_of)
    rec["ai"] = {"calls_models": False, "called": 0, "source": None}
    rec["rows"] = [rr("배정", "", "막힘", "규칙을 지키는 배정이 없음")]
    assert "직접 찾음" not in practice.narrate(assign_unit(), rec, name_of)  # 배정하지 못했으면 찾았다고 쓰지 않음


# ---- 끝 안내(요청 4번) ----

def finish_fixture(mismatch=False, final_ok=True):
    units = units_of("1,지원,s1,1,,,승인,\n2,마감,,,,,승인,\n2,배정,,,,,승인,\n2,확정,,,,,승인,\n")
    v = view([(1, [person(1, PL), person(2, WP)], []), (2, [person(3, PL), person(4, WP)], [])])
    if not final_ok:
        v["teams"][1]["members"] = [person(3, PL)]
    from mp import rules
    final = rules.final_state_checks([{"team_no": t["team_no"], "members": t["members"]} for t in v["teams"]], v["unassigned"])
    records = {u.label: {"rows": [rr(r.action, r.actor, "거절" if mismatch and u.label == "2-2" else "승인") for r in u.rows],
                         "before": v, "after": v, "after_db": v} for u in units}
    records["2-3"]["final_checks"] = final
    return units, records


def test_finish_summary_counts_steps_matches_and_names_the_checks_and_the_teams():
    units, records = finish_fixture()
    fin = practice.finish_summary(units, records)
    assert (fin.steps, fin.units, fin.matched, fin.compared, fin.mismatched) == (2, 4, 4, 4, ())
    assert fin.has_confirm and len(fin.checks) == 4 and all(c["ok"] for c in fin.checks)
    assert fin.teams == (("팀1", ("학생1", "학생2")), ("팀2", ("학생3", "학생4")))


def test_finish_summary_lists_the_substeps_that_differ_from_the_expectation_and_the_rule_violations():
    units, records = finish_fixture(mismatch=True, final_ok=False)
    fin = practice.finish_summary(units, records)
    assert fin.matched == 3 and fin.compared == 4 and fin.mismatched == ("2-2",)
    assert [c["ok"] for c in fin.checks] == [True, False, True, False]


def test_finish_summary_without_a_confirm_step_has_no_checks():
    units = units_of("1,지원,s1,1,,,승인,\n")
    v = view([(1, [person(1)], [])])
    fin = practice.finish_summary(units, {"1": {"rows": [rr("지원", "s1", "승인")], "before": v, "after": v, "after_db": v}})
    assert not fin.has_confirm and fin.checks == () and fin.teams == ()
