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
    return {f"s{i}": f"학생{i}" for i in range(1, 12)}.get(no, no)


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
