# 2026-10-31 11:12 KST
"""연습 시나리오 실행 페이지의 순수 논리 시험(PRD_step4 8장 U-1~U-9, S-1). DB와 네트워크를 쓰지 않음"""
import inspect
import random
import re

import pytest

from conftest import DATA, ROOT
from mp import practice, practice_run, rules
from mp.config import ROLES

HEADER = "step,action,actor,team_no,target,choice,expected,note\n"


def parse(text):
    return practice.parse_steps(("﻿" + HEADER + text).encode("utf-8"))


def errors_of(data):
    with pytest.raises(practice.StepTableError) as e:
        practice.parse_steps(data)
    return e.value.errors


# ---- U-1: CSV 읽기와 검사 ----

def test_parse_reads_rows_and_ignores_bom():
    rows = parse("1,지원,a1,1,,,승인,설명\n1,투표,b1,,a1,찬성,,\n2,마감,,,,,승인,\n")
    assert [(r.step, r.action) for r in rows] == [(1, "지원"), (1, "투표"), (2, "마감")]
    assert rows[0].actor == "a1" and rows[0].team_no == 1 and rows[0].expected == "승인" and rows[0].note == "설명"
    assert rows[1].target == "a1" and rows[1].choice == "찬성" and rows[1].expected == ""
    assert rows[2].actor == "" and rows[2].team_no is None
    assert [r.line for r in rows] == [2, 3, 4]  # 첫 줄은 열 이름


def test_parse_rejects_unknown_action_and_expected():
    errs = errors_of((HEADER + "1,출석,a1,1,,,승인,\n1,지원,a1,1,,,좋음,\n").encode())
    assert any("2줄" in e and "action" in e for e in errs)
    assert any("3줄" in e and "expected" in e for e in errs)


def test_parse_rejects_non_integer_step_and_team_no():
    errs = errors_of((HEADER + "x,지원,a1,1,,,,\n1,지원,a1,팀1,,,,\n").encode())
    assert any("2줄" in e and "step" in e for e in errs)
    assert any("3줄" in e and "team_no" in e for e in errs)


def test_parse_rejects_missing_required_fields():
    errs = errors_of((HEADER + "1,지원,,1,,,,\n1,지원,a1,,,,,\n1,투표,a1,,,찬성,,\n1,투표,a1,,b1,보류,,\n").encode())
    assert any("2줄" in e and "actor" in e for e in errs)
    assert any("3줄" in e and "team_no" in e for e in errs)
    assert any("4줄" in e and "target" in e for e in errs)
    assert any("5줄" in e and "choice" in e for e in errs)


def test_parse_rejects_student_fields_on_admin_actions():
    errs = errors_of((HEADER + "1,마감,a1,,,,,\n").encode())
    assert any("2줄" in e and "마감" in e for e in errs)


def test_parse_rejects_gaps_and_going_back_in_step_numbers():
    assert any("step" in e for e in errors_of((HEADER + "1,마감,,,,,,\n3,배정,,,,,,\n").encode()))
    assert any("step" in e for e in errors_of((HEADER + "2,마감,,,,,,\n").encode()))
    assert any("step" in e for e in errors_of((HEADER + "1,마감,,,,,,\n2,배정,,,,,,\n1,확정,,,,,,\n").encode()))


def test_parse_rejects_wrong_header_empty_file_and_non_utf8():
    assert errors_of(b"")
    assert errors_of("step,action\n1,마감\n".encode())
    assert errors_of(b"\xff\xfe\x00")


def test_parse_rejects_more_than_the_row_limit():
    body = "".join("1,마감,,,,,,\n" for _ in range(practice.MAX_ROWS + 1))
    assert any("행" in e for e in errors_of((HEADER + body).encode()))


def test_parse_collects_all_errors_instead_of_stopping_at_the_first():
    errs = errors_of((HEADER + "1,출석,a1,1,,,,\nx,마감,,,,,,\n").encode())
    assert len(errs) >= 2


@pytest.mark.parametrize("name,rows", [("쉬움", 15), ("중간", 20), ("어려움", 28)])
def test_the_three_data_files_parse(name, rows):
    parsed = practice.parse_steps((DATA / f"{name}_단계.csv").read_bytes())
    assert len(parsed) == rows


def test_check_against_roster_reports_unknown_students_and_teams():
    rows = parse("1,지원,a1,1,,,,\n1,지원,zz,3,,,,\n1,투표,a1,,qq,찬성,,\n")
    errs = practice.check_against_roster(rows, {"a1", "b1"}, 2)
    assert any("3줄" in e and "zz" in e for e in errs)
    assert any("3줄" in e and "팀 번호" in e for e in errs)
    assert any("4줄" in e and "qq" in e for e in errs)
    assert practice.check_against_roster(rows[:1], {"a1"}, 2) == []


# ---- U-2: 판정 ----

def test_judge_row_verdicts():
    assert practice.judge("승인", "승인") == "일치"
    assert practice.judge("승인", "막힘") == "불일치"
    assert practice.judge("", "승인") == "비교 없음"
    assert practice.judge("승인", "막힘", skipped=True) == "건너뜀"
    assert practice.judge("", "막힘", skipped=True) == "건너뜀"


def test_judge_unit_collects_row_verdicts():
    assert practice.judge_unit(["일치", "일치"]) == "일치"
    assert practice.judge_unit(["일치", "불일치", "건너뜀"]) == "불일치"
    assert practice.judge_unit(["비교 없음", "건너뜀"]) == "비교 없음"
    assert practice.judge_unit(["일치", "건너뜀", "비교 없음"]) == "일치"
    assert practice.judge_unit([]) == "비교 없음"


# ---- U-3: 건너뜀 규칙 ----

def test_skip_rule_skips_only_votes_for_a_blocked_applicant():
    t = practice.SkipTracker()
    vote_a = practice.Action("투표", actor="b", target="a", choice="찬성")
    vote_c = practice.Action("투표", actor="b", target="c", choice="찬성")
    assert not t.should_skip(vote_a)
    t.note_result(practice.Action("지원", actor="a", team_no=1), "막힘")
    assert t.should_skip(vote_a)
    assert not t.should_skip(vote_c)
    t.note_result(practice.Action("지원", actor="c", team_no=1), "대기")
    assert not t.should_skip(vote_c)
    assert not t.should_skip(practice.Action("지원", actor="a", team_no=2))  # 지원 행은 건너뛰지 않음


# ---- U-5: 하위 단계 나누기 ----

def units_of(name):
    return practice.split_units(practice.parse_steps((DATA / f"{name}_단계.csv").read_bytes()))


def test_units_of_the_data_files_follow_prd_table():
    easy = [u.label for u in units_of("쉬움")]
    mid = [u.label for u in units_of("중간")]
    hard = [u.label for u in units_of("어려움")]
    assert easy == ["1", "2", "3", "4", "5", "6-1", "6-2", "6-3"]
    assert mid == [str(i) for i in range(1, 11)] + ["11-1", "11-2"]
    assert hard == [str(i) for i in range(1, 15)] + ["15-1", "15-2"]


def test_admin_actions_are_their_own_units_and_students_rows_are_grouped():
    units = units_of("쉬움")
    last3 = units[-3:]
    assert [u.rows[0].action for u in last3] == ["마감", "배정", "확정"]
    assert all(len(u.rows) == 1 for u in last3)
    assert [r.action for r in units[3].rows] == ["지원", "투표", "투표"]


def test_a_step_mixing_student_rows_and_an_admin_row_is_split_in_two():
    units = practice.split_units(parse("1,지원,a1,1,,,,\n1,투표,b1,,a1,찬성,,\n1,마감,,,,,,\n2,배정,,,,,,\n"))
    assert [u.label for u in units] == ["1-1", "1-2", "2"]
    assert [len(u.rows) for u in units] == [2, 1, 1]


def test_unit_key_and_note_for_the_page():
    units = practice.split_units(parse("1,지원,a1,1,,,,첫째\n1,투표,b1,,a1,찬성,,둘째\n2,마감,,,,,,\n2,배정,,,,,,\n"))
    assert units[0].key == "1" and units[0].note == "첫째 / 둘째"
    assert units[1].key == "2_1" and units[2].key == "2_2"


# ---- U-4: 전후 비교 ----

def person(no, name=None, main="기획자", subs=()):
    return {"id": int(no[1:]) if no[1:].isdigit() else hash(no) % 1000, "student_no": no, "name": name or f"학생{no}",
            "main_role": main, "sub_roles": list(subs)}


def view(teams, unassigned=(), phase="open"):
    return {"phase": phase, "unassigned": list(unassigned),
            "teams": [{"id": n, "team_no": n, "name": f"팀{n}", "members": list(m), "pending": list(p)}
                      for n, m, p in teams]}


def pend(no, votes=None):
    d = person(no)
    d["votes"] = votes or {}
    return d


def kinds(changes):
    return sorted((c.kind, c.team_no, c.student_no) for c in changes)


def test_diff_detects_new_and_removed_members():
    before = view([(1, [person("a1")], []), (2, [person("b1"), person("b2")], [])])
    after = view([(1, [person("a1"), person("a2")], []), (2, [person("b1")], [])])
    assert kinds(practice.diff_views(before, after)) == [
        ("빠진 팀원", 2, "b2"), ("새 팀원", 1, "a2")]


def test_diff_detects_pending_applications_and_vote_changes():
    before = view([(1, [person("a1")], [pend("c1")])])
    added = view([(1, [person("a1")], [pend("c1"), pend("c2")])])
    assert kinds(practice.diff_views(before, added)) == [("대기 지원 생김", 1, "c2")]
    gone = view([(1, [person("a1")], [])])
    assert kinds(practice.diff_views(before, gone)) == [("대기 지원 없어짐", 1, "c1")]
    voted = view([(1, [person("a1")], [pend("c1", {1: "찬성"})])])
    changes = practice.diff_views(before, voted)
    assert kinds(changes) == [("찬성 수 변화", 1, "c1")]
    assert "0/1" in changes[0].detail and "1/1" in changes[0].detail


def test_diff_detects_unassigned_students_and_phase():
    before = view([(1, [person("a1")], [])], unassigned=[person("u1")], phase="open")
    after = view([(1, [person("a1")], [])], unassigned=[person("u2")], phase="closed")
    assert kinds(practice.diff_views(before, after)) == [
        ("단계 변화", None, None), ("팀이 없는 학생 생김", None, "u2"), ("팀이 없는 학생 없어짐", None, "u1")]


def test_diff_is_empty_when_nothing_changed():
    v = view([(1, [person("a1")], [pend("c1")])], unassigned=[person("u1")])
    assert practice.diff_views(v, v) == []


# ---- U-6: 배정안 얹기 ----

def test_apply_proposal_moves_unassigned_students_into_teams_without_touching_the_original():
    v = view([(1, [person("a1")], []), (2, [person("b1", main="웹 프로그래머")], [])],
             unassigned=[person("u1", main="웹 프로그래머"), person("u2", main="테스터")], phase="closed")
    out = practice.apply_proposal(v, [("u1", 1), ("u2", 2)])
    assert [m["student_no"] for m in out["teams"][0]["members"]] == ["a1", "u1"]
    assert [m["student_no"] for m in out["teams"][1]["members"]] == ["b1", "u2"]
    assert out["unassigned"] == []
    assert out["teams"][0]["members"][1]["proposed"] is True
    assert "proposed" not in out["teams"][0]["members"][0]
    assert len(v["unassigned"]) == 2 and len(v["teams"][0]["members"]) == 1  # 원본 그대로
    changes = practice.diff_views(v, out)
    assert ("새 팀원", 1, "u1") in kinds(changes) and ("팀이 없는 학생 없어짐", None, "u2") in kinds(changes)


# ---- U-7: 배정 검사 5가지 ----

def student(i, main, subs=()):
    return {"id": i, "student_no": f"s{i}", "name": f"s{i}", "main_role": main, "sub_roles": list(subs)}


def sample():
    teams = [{"team_no": 1, "members": [student(1, "기획자")]}, {"team_no": 2, "members": [student(2, "웹 프로그래머")]}]
    unassigned = [student(3, "웹 프로그래머"), student(4, "기획자")]
    return teams, unassigned


def test_assignment_checks_all_pass_for_a_valid_assignment():
    teams, un = sample()
    checks = rules.assignment_checks(teams, un, [("s3", 1), ("s4", 2)])
    assert [c["no"] for c in checks] == [1, 2, 3, 4, 5]
    assert all(c["ok"] for c in checks)
    assert rules.check_assignment(teams, un, [("s3", 1), ("s4", 2)]) is None


def test_assignment_checks_fail_each_check_separately():
    teams, un = sample()
    ok = lambda pairs: [c["ok"] for c in rules.assignment_checks(teams, un, pairs)]
    assert ok([("s3", 1)])[0] is False  # 1번: 배정되지 않은 학생이 있음
    assert ok([("s3", 1), ("s4", 2), ("s9", 1)])[0] is False  # 1번: 팀이 없는 학생이 아닌 학번
    assert ok([("s3", 1), ("s3", 2), ("s4", 2)])[1] is False  # 2번: 두 번 배정
    assert ok([("s3", 1), ("s4", 7)])[1] is False  # 2번: 없는 팀
    teams[0]["members"] = [student(1, "기획자"), student(5, "테스터"), student(6, "발표자"), student(7, "보고서 작성자")]
    assert ok([("s3", 1), ("s4", 2)])[2] is False  # 3번: 팀1이 5명
    teams[0]["members"] = [student(1, "기획자")]
    assert ok([("s4", 1), ("s3", 2)])[3] is False  # 4번: 팀1에 기획자 2명
    un[0] = student(3, "테스터")
    assert ok([("s3", 1), ("s4", 2)])[4] is False  # 5번: 팀1이 기획자(1)와 테스터(3)뿐이라 웹 프로그래머가 없음


def test_assignment_checks_agree_with_check_assignment_on_random_assignments():
    rng = random.Random(7)
    for _ in range(300):
        n_teams = rng.randint(2, 4)
        teams = [{"team_no": t, "members": [student(100 * t + k, rng.choice(ROLES)) for k in range(rng.randint(0, 2))]}
                 for t in range(1, n_teams + 1)]
        un = [student(1000 + i, rng.choice(ROLES), rng.sample(ROLES, rng.randint(0, 2))) for i in range(rng.randint(1, 6))]
        un = [dict(u, sub_roles=[r for r in u["sub_roles"] if r != u["main_role"]]) for u in un]
        pairs = [(u["student_no"], rng.randint(1, n_teams + 1)) for u in un if rng.random() > 0.1]
        if pairs and rng.random() < 0.2:
            pairs.append(pairs[0])
        checks = rules.assignment_checks(teams, un, pairs)
        problem = rules.check_assignment(teams, un, pairs)
        assert (problem is None) == all(c["ok"] for c in checks), (problem, checks)
        if problem:
            number = int(re.match(r"검사 (\d)번", problem).group(1))
            assert checks[number - 1]["ok"] is False, (problem, checks)


def test_assignment_checks_pass_for_what_the_app_finds_itself():
    rng = random.Random(3)
    found = 0
    for _ in range(60):
        teams = [{"team_no": t, "members": []} for t in (1, 2)]
        un = [student(i, rng.choice(ROLES), rng.sample(ROLES, 1)) for i in range(1, rng.randint(4, 8))]
        un = [dict(u, sub_roles=[r for r in u["sub_roles"] if r != u["main_role"]]) for u in un]
        pairs, _ = rules.find_assignment(teams, un)
        if pairs:
            found += 1
            assert all(c["ok"] for c in rules.assignment_checks(teams, un, pairs))
    assert found > 0


# ---- U-8: 확정한 팀 구성의 규칙 확인 4가지 ----

def test_final_state_checks_pass_and_fail_each_check_separately():
    good = [{"team_no": 1, "members": [student(1, "기획자"), student(2, "웹 프로그래머")]},
            {"team_no": 2, "members": [student(3, "기획자"), student(4, "웹 프로그래머"), student(5, "테스터")]}]
    checks = rules.final_state_checks(good, [])
    assert [c["no"] for c in checks] == [1, 2, 3, 4] and all(c["ok"] for c in checks)
    assert rules.final_state_checks(good, [student(9, "발표자")])[0]["ok"] is False  # 팀이 없는 학생이 남음
    small = [good[0], {"team_no": 2, "members": [student(3, "기획자")]}]
    assert rules.final_state_checks(small, [])[1]["ok"] is False  # 1명인 팀
    dup = [good[0], {"team_no": 2, "members": [student(3, "기획자"), student(4, "기획자", ["웹 프로그래머"])]}]
    assert rules.final_state_checks(dup, [])[2]["ok"] is False  # 주 역할 중복
    noweb = [good[0], {"team_no": 2, "members": [student(3, "기획자"), student(4, "테스터")]}]
    assert rules.final_state_checks(noweb, [])[3]["ok"] is False  # 웹 프로그래머 없음


def named(no, main, subs=()):
    return dict(student(no, main, list(subs)), name=f"학생{no}(약자)")


def test_a_violation_names_every_team_and_every_student_at_fault():
    teams = [{"team_no": 1, "members": [named(1, "기획자"), named(2, "테스터"), named(3, "테스터")]},
             {"team_no": 2, "members": [named(4, "발표자")]},
             {"team_no": 3, "members": [named(5, "기획자"), named(6, "기획자"), named(7, "웹 프로그래머")]},
             {"team_no": 4, "members": [named(8, "웹 프로그래머"), named(9, "발표자")]}]
    checks = rules.final_state_checks(teams, [named(10, "테스터"), named(11, "보고서 작성자")])
    assert [c["ok"] for c in checks] == [False, False, False, False]
    assert checks[0]["detail"] == "팀이 없는 학생 2명이 남음(학생10, 학생11)"
    assert checks[1]["detail"] == "팀2(학생4)은 1명임(2~4명이어야 함)"
    assert checks[2]["detail"] == "팀1에서 학생2, 학생3의 주 역할이 테스터로 같음; 팀3에서 학생5, 학생6의 주 역할이 기획자로 같음"
    assert checks[3]["detail"] == ("팀1(학생1, 학생2, 학생3)의 필수 포함 역할(기획자, 웹 프로그래머)을 채울 수 없음; "
                                   "팀2(학생4)의 필수 포함 역할(기획자, 웹 프로그래머)을 채울 수 없음; "
                                   "팀4(학생8, 학생9)의 필수 포함 역할(기획자, 웹 프로그래머)을 채울 수 없음")


def test_the_assignment_checks_also_name_every_team_and_student_at_fault():
    teams = [{"team_no": 1, "members": [named(1, "기획자")]}, {"team_no": 2, "members": [named(2, "기획자")]}]
    un = [named(3, "기획자"), named(4, "테스터"), named(5, "발표자")]
    checks = rules.assignment_checks(teams, un, [("s3", 1), ("s3", 2), ("s4", 9)])
    assert checks[0]["ok"] is False and "학생5" in checks[0]["detail"]
    assert checks[1]["ok"] is False and "학생3" in checks[1]["detail"] and "팀9" in checks[1]["detail"]
    placed = rules.assignment_checks(teams, un, [("s3", 1), ("s4", 1), ("s5", 1)])
    assert placed[3]["detail"] == "팀1에서 학생1, 학생3의 주 역할이 기획자로 같음"
    assert "팀2(학생2)은 1명임" in placed[2]["detail"]


# ---- U-9: AI 호출 한도 ----

def test_quota_blocks_above_the_daily_limit_and_warns_below_the_reserve():
    assert (practice.DAILY_LIMIT, practice.RESERVE, practice.CALLS_PER_RUN) == (50, 30, 3)
    q = practice.quota(48)
    assert q.blocked is True
    q = practice.quota(47)
    assert q.blocked is False and q.warn is True and q.remaining_after == 0
    q = practice.quota(18)
    assert q.blocked is False and q.warn is True and q.remaining_after == 29
    q = practice.quota(17)
    assert q.blocked is False and q.warn is False and q.remaining_after == 30
    q = practice.quota(0)
    assert q.blocked is False and q.warn is False and q.remaining_after == 47


# ---- S-1: 소스 검색(감점 19번을 피하는 규칙 1, 4) ----

APP_SOURCES = [ROOT / "streamlit_app.py", *sorted((ROOT / "mp").glob("*.py")), *sorted((ROOT / "pages").glob("*.py"))]


def test_app_code_has_no_practice_scenario_literals():
    assert any(p.name == "practice.py" for p in APP_SOURCES), "pages/practice.py와 mp/practice.py가 있어야 검색 대상이 됨"
    found = []
    for path in APP_SOURCES:
        text = path.read_text(encoding="utf-8")
        for pattern in (r"\b20\d{5}\b", r"학생\d+\(", r"tests/data", r"_단계\.csv"):
            for m in re.finditer(pattern, text):
                found.append((path.name, pattern, text[max(0, m.start() - 20): m.end() + 10]))
    assert found == []


# ---- S-2(일부): 실행 함수는 기대 결과를 받지 않음 ----

def test_run_unit_takes_no_expected_results_and_actions_carry_none():
    params = set(inspect.signature(practice_run.run_unit).parameters)
    assert not {"expected", "rows", "row", "unit"} & params
    assert not {"expected", "note"} & set(practice.Action.__dataclass_fields__)
    row = parse("1,지원,a1,1,,,승인,설명\n")[0]
    action = row.to_action()
    assert not hasattr(action, "expected") and not hasattr(action, "note")


# ---- 단계표의 "하는 일", "기대 결과" 열(2026-11-01) ----

TEXT_STEPS = ("step,action,actor,team_no,target,choice,expected,note,하는 일,기대 결과\n"
              "1,지원,a1,1,,,승인,n,\"a1이 팀1에, b1이 팀2에 지원\",2명 모두 바로 승인\n"
              "1,지원,b1,2,,,승인,n,,\n"
              "2,마감,,,,,승인,n,관리자가 마감하고 배정,남은 학생이 모두 배정됨\n"
              "2,배정,,,,,승인,n,,\n")


def test_the_step_table_may_have_the_two_text_columns_and_the_units_carry_the_sentences():
    rows = practice.parse_steps(TEXT_STEPS.encode("utf-8"))
    assert rows[0].plan == "a1이 팀1에, b1이 팀2에 지원" and rows[0].expect_text == "2명 모두 바로 승인"
    assert rows[1].plan == "" and rows[1].expect_text == ""
    units = practice.split_units(rows)
    assert [(u.label, u.plan, u.expect_text, u.step_units) for u in units] == [
        ("1", "a1이 팀1에, b1이 팀2에 지원", "2명 모두 바로 승인", 1),
        ("2-1", "관리자가 마감하고 배정", "남은 학생이 모두 배정됨", 2),
        ("2-2", "관리자가 마감하고 배정", "남은 학생이 모두 배정됨", 2)]


def test_a_step_table_without_the_text_columns_still_works():
    rows = practice.parse_steps(("step,action,actor,team_no,target,choice,expected,note\n1,지원,a1,1,,,승인,n\n").encode("utf-8"))
    assert rows[0].plan == "" and rows[0].expect_text == ""
    (unit,) = practice.split_units(rows)
    assert unit.plan == "" and unit.expect_text == "" and unit.step_units == 1


def test_a_header_with_only_one_of_the_text_columns_is_refused():
    with pytest.raises(practice.StepTableError):
        practice.parse_steps(b"step,action,actor,team_no,target,choice,expected,note,\xed\x95\x98\xeb\x8a\x94 \xec\x9d\xbc\n1,\xec\xa7\x80\xec\x9b\x90,a1,1,,,,,x\n")


def test_the_practice_step_tables_carry_the_appendix_sentences_in_the_first_row_of_each_step():
    from conftest import DATA
    for name, steps in (("쉬움", 6), ("중간", 11), ("어려움", 15)):
        rows = practice.parse_steps((DATA / f"{name}_단계.csv").read_bytes())
        units = practice.split_units(rows)
        assert len({u.step for u in units}) == steps
        assert all(u.plan and u.expect_text for u in units), name
    easy = practice.parse_steps((DATA / "쉬움_단계.csv").read_bytes())
    assert easy[0].plan == "학생1(PL;RW)이 팀1에, 학생2(PL;PT)가 팀2에, 학생3(PL;TT)이 팀3에 지원"
    assert easy[0].expect_text == "3명 모두 바로 승인"


# ---- 준비 칸의 검사(요청 1번): 입력이 바뀔 때마다 다시 검사함 ----

ROSTER = "student_no,name,main_role,sub_roles\na1,A,기획자,\nb1,B,웹 프로그래머,\n".encode("utf-8")
STEPS = ("step,action,actor,team_no,target,choice,expected,note\n"
         "1,지원,a1,3,,,승인,\n2,지원,b1,4,,,승인,\n").encode("utf-8")


def test_a_team_count_that_is_too_small_is_an_error_that_names_the_team_numbers():
    check = practice.prep_check(ROSTER, STEPS, 2)
    assert check.errors == ("단계표 CSV: 팀 번호 3, 4가 팀 수(2)보다 큼",) and not check.ready
    assert practice.prep_check(ROSTER, STEPS, 3).errors == ("단계표 CSV: 팀 번호 4가 팀 수(3)보다 큼",)


def test_fixing_the_team_count_clears_the_error_and_the_start_becomes_possible():
    assert practice.prep_check(ROSTER, STEPS, 4).errors == () and practice.prep_check(ROSTER, STEPS, 4).ready


def test_a_team_count_larger_than_the_step_table_uses_is_a_yellow_warning_not_an_error():
    check = practice.prep_check(ROSTER, STEPS, 5)
    assert check.errors == () and check.ready
    assert check.warning == "단계표는 팀 4개를 씀. 팀 5개로 하면 팀5가 빈 채로 시작해 결과가 공고 부록과 달라질 수 있음"
    assert practice.prep_check(ROSTER, STEPS, 6).warning.startswith("단계표는 팀 4개를 씀. 팀 6개로 하면 팀5, 팀6이 빈 채로")
    assert "팀5~팀100이 빈 채로" in practice.prep_check(ROSTER, STEPS, 100).warning
    assert practice.prep_check(ROSTER, STEPS, 4).warning == ""


def test_the_other_problems_stay_until_they_are_fixed_and_the_team_count_does_not_hide_them():
    bad_roster = b"student_no,name,main_role,sub_roles\n1,A,\xeb\x8f\x84\xeb\x91\x91,\n"
    check = practice.prep_check(bad_roster, STEPS, 4)
    assert any(e.startswith("명단 CSV:") for e in check.errors) and not check.ready
    unknown = ("step,action,actor,team_no,target,choice,expected,note\n1,지원,zz,1,,,승인,\n").encode("utf-8")
    assert any("zz가 명단에 없음" in e for e in practice.prep_check(ROSTER, unknown, 4).errors)
    assert practice.prep_check(ROSTER, b"step,x\n", 4).errors[0].startswith("단계표 CSV 열이")


def test_without_both_files_nothing_is_wrong_but_the_start_is_not_ready():
    assert practice.prep_check(None, None, 3).errors == () and not practice.prep_check(None, None, 3).ready
    assert practice.prep_check(ROSTER, None, 3).ready is False
    assert practice.prep_check(None, STEPS, 4).max_team == 4


def test_the_team_range_text():
    assert practice.team_range_text(1, 4) == "팀1~팀4" and practice.team_range_text(2, 2) == "팀2"


class FakeUpload:
    def __init__(self, name, data, file_id):
        self.name, self.file_id, self._data, self.size = name, file_id, data, len(data)

    def getvalue(self):
        return self._data


def test_uploading_a_step_table_sets_the_team_count_to_the_largest_team_number_once(monkeypatch):
    from mp import practice_view
    state = {}
    monkeypatch.setattr(practice_view, "S", state)
    state["practice_team_count"] = 3
    state["practice_steps_file"] = FakeUpload("a.csv", STEPS, "id-1")
    practice_view.sync_team_count()
    assert state["practice_team_count"] == 4
    assert state["practice_auto_team"] == (4, "단계표가 팀3~팀4를 쓰므로 팀 수를 4로 맞춤")
    state["practice_team_count"] = 5  # 사람이 바꾼 값은 같은 파일이면 그대로 둠
    practice_view.sync_team_count()
    assert state["practice_team_count"] == 5
    other = STEPS.replace(b",4,,,", b",2,,,")
    state["practice_steps_file"] = FakeUpload("b.csv", other, "id-2")  # 다른 파일을 올리면 다시 맞춤
    practice_view.sync_team_count()
    assert state["practice_team_count"] == 3 and state["practice_auto_team"][0] == 3
    del state["practice_steps_file"]
    practice_view.sync_team_count()
    assert "practice_auto_team" not in state and "practice_steps_seen" not in state
