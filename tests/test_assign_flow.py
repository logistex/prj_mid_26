# 2026-10-30 23:05 KST
"""배정 흐름 시험(PRD_step3 10.1절~10.4절). 실제 Supabase DB의 tf_mp_ 테이블을 쓰고, AI 호출은 가짜 함수로 대신함

실제 OpenRouter 호출은 하지 않음. 쉬움.csv(학생 8명, 팀 3개)를 부록 1 단계 5까지 진행한 뒤 마감한 상태에서 시작함
"""
import json

import pytest

from conftest import DATA
from mp import ai, service
from mp.config import get_secret
from mp.db import make_pool

pytestmark = pytest.mark.skipif(
    not (get_secret("DATABASE_URL") and get_secret("ADMIN_PASSWORD")), reason="DATABASE_URL 또는 ADMIN_PASSWORD 없음"
)

BASE = 2026100
MODELS = ("m1:free", "m2:free", "m3:free")


def no(i):
    return str(BASE + i)


@pytest.fixture(scope="module")
def pool():
    p = make_pool(get_secret("DATABASE_URL"))
    service.ensure_admin(p, get_secret("ADMIN_PASSWORD"))
    yield p
    p.close()


def uid(pool, student_no):
    with pool.connection() as conn:
        return conn.execute("select id from tf_mp_students where student_no = %s", (student_no,)).fetchone()[0]


def admin(pool):
    return uid(pool, "admin")


def seat(pool, i, team_no):
    res = service.apply_to_team(pool, uid(pool, no(i)), team_no)
    if res.status == "대기":
        with pool.connection() as conn:
            members = [r[0] for r in conn.execute(
                "select s.student_no from tf_mp_members m join tf_mp_teams t on t.id = m.team_id"
                " join tf_mp_students s on s.id = m.student_id where t.team_no = %s", (team_no,)).fetchall()]
        for member in members:
            res = service.vote(pool, uid(pool, member), no(i), "찬성")
    assert res.status == "승인", res.text


@pytest.fixture
def closed_easy(pool):
    """부록 1 단계 5까지 진행하고 마감한 상태: 학생1~6이 팀에 있고 학생7, 8이 팀이 없음"""
    assert service.start_roster(pool, admin(pool), (DATA / "쉬움.csv").read_bytes(), 3).ok
    for i, team in ((1, 1), (2, 2), (3, 3), (4, 1), (5, 2), (6, 3)):
        seat(pool, i, team)
    assert service.close_recruitment(pool, admin(pool)).ok
    return pool


def scripted_ask(*outcomes):
    """Attempt 결과를 순서대로 돌려주는 가짜 호출 함수. 호출한 모델 이름을 called에 모음"""
    called = []

    def ask(n, model, tick):
        called.append(model)
        outcome, pairs = outcomes[n - 1]
        return ai.Attempt(model, outcome, 0.5 * n, "" if outcome == ai.SUCCESS else "가짜 실패", pairs or [])

    ask.called = called
    return ask


def count(pool, sql, args=()):
    with pool.connection() as conn:
        return conn.execute(sql, args).fetchone()[0]


def final_teams(pool):
    with pool.connection() as conn:
        rows = conn.execute(
            "select t.team_no, s.student_no, s.main_role,"
            " coalesce((select array_agg(r.role) from tf_mp_student_sub_roles r where r.student_id = s.id), '{}')"
            " from tf_mp_members m join tf_mp_teams t on t.id = m.team_id join tf_mp_students s on s.id = m.student_id"
            " order by t.team_no, m.slot_no"
        ).fetchall()
    teams = {}
    for team_no, student_no, main_role, subs in rows:
        teams.setdefault(team_no, []).append({"id": student_no, "main_role": main_role, "sub_roles": list(subs)})
    return teams


def assert_rules_hold(pool):
    """확정한 팀 구성이 공고 2.3절을 지키는지: 팀 수, 인원 2~4명, 주 역할 중복 없음, 필수 포함 역할 충족, 학생이 모두 한 팀에 있음"""
    from mp import rules
    teams = final_teams(pool)
    assert teams
    total_students = count(pool, "select count(*) from tf_mp_students where not is_admin")
    assert sum(len(m) for m in teams.values()) == total_students
    for team_no, members in teams.items():
        assert 2 <= len(members) <= 4, f"팀{team_no} 인원 {len(members)}"
        mains = [m["main_role"] for m in members]
        assert len(set(mains)) == len(mains), f"팀{team_no} 주 역할 중복"
        assert rules.required_deficit(members) == 0, f"팀{team_no} 필수 포함 역할 부족"
    assert count(pool, "select count(*) from (select student_id from tf_mp_members group by student_id having count(*) > 1) x") == 0


def test_blocked_before_close_and_for_students(pool):
    assert service.start_roster(pool, admin(pool), (DATA / "쉬움.csv").read_bytes(), 3).ok
    assert service.prepare_assignment(pool, admin(pool)).result.text == "막힘: 모집을 마감한 뒤에 배정할 수 있음"
    assert service.prepare_assignment(pool, uid(pool, no(1))).result.text == "막힘: 관리자만 할 수 있음"
    assert service.confirm_assignment(pool, admin(pool)).text == "막힘: 모집을 마감한 뒤에 확정할 수 있음"
    assert service.confirm_assignment(pool, uid(pool, no(1))).text == "막힘: 관리자만 할 수 있음"


def test_first_model_success_saves_a_proposal_and_one_log_row(closed_easy):
    pool = closed_easy
    before = count(pool, "select count(*) from tf_mp_ai_logs")
    prep = service.prepare_assignment(pool, admin(pool))
    assert prep.result is None and prep.fallback
    ask = scripted_ask((ai.SUCCESS, prep.fallback))
    progress = ai.Progress()
    res = service.generate_proposal(pool, prep, ask, MODELS, 120, progress)
    assert res.text == "승인: 배정안을 만듦(1차 모델(m1:free))"
    assert ask.called == ["m1:free"]  # 2차, 3차는 부르지 않음
    assert count(pool, "select count(*) from tf_mp_ai_logs") == before + 1
    proposal = service.load_proposal(pool)
    assert proposal["source"] == "1차 모델(m1:free)"
    assert {n for n, _ in proposal["pairs"]} == {no(7), no(8)}
    assert "검사를 통과한 배정안을 만듦" in service.get_setting(pool, "assign_status")


def test_first_two_fail_third_succeeds_and_all_attempts_are_logged(closed_easy):
    pool = closed_easy
    before = count(pool, "select count(*) from tf_mp_ai_logs")
    prep = service.prepare_assignment(pool, admin(pool))
    ask = scripted_ask((ai.TIMEOUT, None), (ai.HTTP_ERROR, None), (ai.SUCCESS, prep.fallback))
    res = service.generate_proposal(pool, prep, ask, MODELS, 120, ai.Progress())
    assert "3차 모델(m3:free)" in res.text
    assert ask.called == list(MODELS)
    rows = service.recent_ai_logs(pool, 3)[::-1]
    assert [(r[1], r[3]) for r in rows] == [(1, ai.TIMEOUT), (2, ai.HTTP_ERROR), (3, ai.SUCCESS)]
    assert count(pool, "select count(*) from tf_mp_ai_logs") == before + 3


def test_all_three_fail_so_the_app_assigns_by_itself(closed_easy):
    pool = closed_easy
    prep = service.prepare_assignment(pool, admin(pool))
    ask = scripted_ask((ai.TIMEOUT, None), (ai.EMPTY, None), (ai.CHECK_FAILED, [(no(7), 1), (no(8), 1)]))
    progress = ai.Progress()
    res = service.generate_proposal(pool, prep, ask, MODELS, 120, progress)
    assert res.text == "승인: 배정안을 만듦(앱이 직접 배정)"
    assert service.load_proposal(pool)["source"] == "앱이 직접 배정"
    status = service.get_setting(pool, "assign_status")
    assert "1차 모델: 시간 초과" in status and "3차까지 실패해 앱이 직접 배정함" in status


def test_confirm_saves_the_teams_and_they_keep_the_rules(closed_easy):
    pool = closed_easy
    prep = service.prepare_assignment(pool, admin(pool))
    service.generate_proposal(pool, prep, scripted_ask((ai.SUCCESS, prep.fallback)), MODELS, 120, ai.Progress())
    res = service.confirm_assignment(pool, admin(pool))
    assert res.text == "승인: 배정안을 확정함"
    assert service.get_setting(pool, "phase") == "confirmed"
    assert service.load_proposal(pool) is None
    assert service.get_setting(pool, "assign_status") == "배정안을 확정함"
    assert_rules_hold(pool)
    # 확정한 뒤: 다시 확정, 다시 배정, 지원은 막힘
    assert service.confirm_assignment(pool, admin(pool)).text == "막힘: 이미 확정함"
    assert service.prepare_assignment(pool, admin(pool)).result.text == "막힘: 이미 확정함"
    assert service.apply_to_team(pool, uid(pool, no(7)), 1).text == "막힘: 모집이 마감됨"
    # 새 세션(연결)으로 읽어도 팀 구성이 그대로임
    view = service.load_view(pool)
    assert sum(len(t["members"]) for t in view["teams"]) == 8 and view["unassigned"] == []


def test_confirm_without_proposal_is_blocked(closed_easy):
    assert service.confirm_assignment(closed_easy, admin(closed_easy)).text == "막힘: 확정할 배정안이 없음"


def test_a_stale_proposal_is_not_confirmed(closed_easy):
    pool = closed_easy
    prep = service.prepare_assignment(pool, admin(pool))
    service.generate_proposal(pool, prep, scripted_ask((ai.SUCCESS, prep.fallback)), MODELS, 120, ai.Progress())
    # 배정안을 만든 뒤 팀 구성이 바뀐 것으로 만듦: 학생7을 직접 팀1에 넣음
    with pool.connection() as conn:
        conn.execute(
            "insert into tf_mp_members (team_id, slot_no, student_id)"
            " select t.id, 3, s.id from tf_mp_teams t, tf_mp_students s where t.team_no = 1 and s.student_no = %s",
            (no(7),),
        )
    res = service.confirm_assignment(pool, admin(pool))
    assert res.text == "막힘: 배정안이 현재 팀 구성과 맞지 않음. 다시 배정해야 함"
    assert service.get_setting(pool, "phase") == "closed"
    assert count(pool, "select count(*) from tf_mp_members") == 7  # 확정이 일부만 저장되지 않음


def test_no_valid_assignment_skips_the_ai_and_explains(pool):
    # 웹 프로그래머를 맡을 수 있는 학생이 아무도 없는 명단: 팀 2개, 학생 4명
    roster = (
        "student_no,name,main_role,sub_roles\n"
        "9001,가,기획자,\n9002,나,테스터,\n9003,다,발표자,\n9004,라,보고서 작성자,\n"
    ).encode("utf-8")
    assert service.start_roster(pool, admin(pool), roster, 2).ok
    assert service.close_recruitment(pool, admin(pool)).ok
    prep = service.prepare_assignment(pool, admin(pool))
    assert prep.result.text == "막힘: 규칙을 지키는 배정이 없음"
    assert service.get_setting(pool, "assign_status") == "규칙을 지키는 배정이 없음: 팀1에 웹 프로그래머를 맡을 학생이 없음"
    assert service.load_proposal(pool) is None
    assert service.confirm_assignment(pool, admin(pool)).text == "막힘: 확정할 배정안이 없음"


def test_no_unassigned_students_is_blocked(pool):
    roster = "student_no,name,main_role,sub_roles\n9001,가,기획자,\n9002,나,웹 프로그래머,\n".encode("utf-8")
    assert service.start_roster(pool, admin(pool), roster, 1).ok
    seat_res = service.apply_to_team(pool, uid(pool, "9001"), 1)
    assert seat_res.status == "승인"
    assert service.apply_to_team(pool, uid(pool, "9002"), 1).status == "대기"
    service.vote(pool, uid(pool, "9001"), "9002", "찬성")
    assert service.close_recruitment(pool, admin(pool)).ok
    assert service.prepare_assignment(pool, admin(pool)).result.text == "막힘: 팀이 없는 학생이 없음"


def test_roster_reset_clears_proposal_and_status_but_keeps_ai_logs(closed_easy):
    pool = closed_easy
    prep = service.prepare_assignment(pool, admin(pool))
    service.generate_proposal(pool, prep, scripted_ask((ai.SUCCESS, prep.fallback)), MODELS, 120, ai.Progress())
    logs_before = count(pool, "select count(*) from tf_mp_ai_logs")
    assert service.get_setting(pool, "proposal") and service.get_setting(pool, "assign_status")
    assert service.start_roster(pool, admin(pool), (DATA / "쉬움.csv").read_bytes(), 3).ok
    assert service.get_setting(pool, "proposal") is None
    assert service.get_setting(pool, "assign_status") is None
    assert count(pool, "select count(*) from tf_mp_ai_logs") == logs_before  # README 근거라서 지우지 않음


def test_proposal_without_check_pass_is_never_shown(closed_easy):
    # 앱 자체 배정마저 검사를 통과하지 못하는 경우(fallback이 잘못 들어옴)는 proposal을 저장하지 않음
    pool = closed_easy
    prep = service.prepare_assignment(pool, admin(pool))
    prep.fallback = [(no(7), 1)]  # 학생8이 빠짐
    ask = scripted_ask((ai.TIMEOUT, None), (ai.TIMEOUT, None), (ai.TIMEOUT, None))
    res = service.generate_proposal(pool, prep, ask, MODELS, 120, ai.Progress())
    assert res.status == "막힘"
    assert service.load_proposal(pool) is None
