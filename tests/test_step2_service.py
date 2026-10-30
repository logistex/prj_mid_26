# 2026-10-30 22:55 KST
"""2단계 서비스 시험(PRD_step2 10.1절 판정, 10.3절 동시성). 실제 Supabase DB의 tf_mp_ 테이블을 씀

중간.csv(학생 12명, 팀 4개)로 시작함. 학생 번호는 2026200 + 순번임
"""
import threading

import pytest

from conftest import DATA
from mp import service
from mp.config import get_secret
from mp.db import make_pool

pytestmark = pytest.mark.skipif(
    not (get_secret("DATABASE_URL") and get_secret("ADMIN_PASSWORD")), reason="DATABASE_URL 또는 ADMIN_PASSWORD 없음"
)

BASE = 2026200


def no(i):
    return str(BASE + i)


@pytest.fixture(scope="module")
def pool():
    p = make_pool(get_secret("DATABASE_URL"))
    service.ensure_admin(p, get_secret("ADMIN_PASSWORD"))
    yield p
    p.close()


@pytest.fixture
def fresh(pool):
    _, admin_id = service.login(pool, "admin", get_secret("ADMIN_PASSWORD"))
    assert service.start_roster(pool, admin_id, (DATA / "중간.csv").read_bytes(), 4).ok
    return pool


def uid(pool, student_no):
    with pool.connection() as conn:
        return conn.execute("select id from tf_mp_students where student_no = %s", (student_no,)).fetchone()[0]


def admin(pool):
    return service.login(pool, "admin", get_secret("ADMIN_PASSWORD"))[1]


def team_member_nos(pool, team_no):
    with pool.connection() as conn:
        rows = conn.execute(
            "select s.student_no from tf_mp_members m join tf_mp_teams t on t.id = m.team_id"
            " join tf_mp_students s on s.id = m.student_id where t.team_no = %s order by m.slot_no", (team_no,)
        ).fetchall()
    return [r[0] for r in rows]


def count(pool, sql, args=()):
    with pool.connection() as conn:
        return conn.execute(sql, args).fetchone()[0]


def seat(pool, i, team_no):
    """학생 i를 팀에 넣음. 대기이면 그때의 팀원 전원이 찬성함"""
    res = service.apply_to_team(pool, uid(pool, no(i)), team_no)
    if res.status == "대기":
        for member in team_member_nos(pool, team_no):
            res = service.vote(pool, uid(pool, member), no(i), "찬성")
    assert res.status == "승인", f"학생{i}를 팀{team_no}에 넣지 못함: {res.text}"


def votes_of(pool, applicant_i):
    return count(
        pool,
        "select count(*) from tf_mp_votes v join tf_mp_applications a on a.id = v.application_id"
        " join tf_mp_students s on s.id = a.student_id where s.student_no = %s", (no(applicant_i),),
    )


def test_vote_on_a_rejected_application_shows_its_state_and_records_nothing(fresh):
    # 화면이 3초 늦게 갱신되는 사이에 이미 거절된 지원에 찬성을 누르는 경우(공고 2.7절)
    seat(fresh, 1, 1)
    seat(fresh, 5, 1)
    assert service.apply_to_team(fresh, uid(fresh, no(9)), 1).status == "대기"
    assert service.vote(fresh, uid(fresh, no(1)), no(9), "거부").text == "거절: 팀원이 거부함"
    late = service.vote(fresh, uid(fresh, no(5)), no(9), "찬성")
    assert late.text == "거절: 팀원이 거부함"
    assert votes_of(fresh, 9) == 1  # 늦게 누른 투표는 기록하지 않음


def test_vote_on_an_approved_application_shows_approval(fresh):
    seat(fresh, 1, 1)
    assert service.apply_to_team(fresh, uid(fresh, no(5)), 1).status == "대기"
    assert service.vote(fresh, uid(fresh, no(1)), no(5), "찬성").status == "승인"
    assert service.vote(fresh, uid(fresh, no(1)), no(5), "찬성").status == "승인"
    assert votes_of(fresh, 5) == 1


def test_double_vote_is_blocked_while_waiting(fresh):
    seat(fresh, 1, 1)
    seat(fresh, 5, 1)
    service.apply_to_team(fresh, uid(fresh, no(9)), 1)
    assert service.vote(fresh, uid(fresh, no(1)), no(9), "찬성").status == "대기"
    again = service.vote(fresh, uid(fresh, no(1)), no(9), "찬성")
    assert again.text == "막힘: 이미 투표함(바꿀 수 없음)"
    assert votes_of(fresh, 9) == 1


def test_only_team_members_can_vote(fresh):
    seat(fresh, 1, 1)
    service.apply_to_team(fresh, uid(fresh, no(5)), 1)
    seat(fresh, 6, 2)
    for voter in (5, 6, 12):  # 지원자 본인, 다른 팀의 팀원, 팀이 없는 학생
        res = service.vote(fresh, uid(fresh, no(voter)), no(5), "찬성")
        assert res.text == "막힘: 이 팀의 팀원만 투표할 수 있음"
    assert votes_of(fresh, 5) == 0


def test_vote_without_application_and_bad_choice_are_blocked(fresh):
    assert service.vote(fresh, uid(fresh, no(1)), no(12), "찬성").text == "막힘: 지원이 없음"
    assert service.vote(fresh, uid(fresh, no(1)), no(12), "기권").status == "막힘"


def test_vote_after_close_shows_rejection_reason(fresh):
    seat(fresh, 1, 1)
    service.apply_to_team(fresh, uid(fresh, no(5)), 1)
    assert service.close_recruitment(fresh, admin(fresh)).ok
    assert service.vote(fresh, uid(fresh, no(1)), no(5), "찬성").text == "거절: 모집 마감"


def test_apply_blocked_messages(fresh):
    seat(fresh, 1, 1)
    assert service.apply_to_team(fresh, uid(fresh, no(1)), 2).text == "막힘: 이미 팀이 있음"
    assert service.apply_to_team(fresh, uid(fresh, no(2)), 1).text == "막힘: 같은 주 역할의 팀원이 있음"
    assert service.apply_to_team(fresh, admin(fresh), 1).text == "막힘: 학생만 지원할 수 있음"
    assert service.apply_to_team(fresh, uid(fresh, no(5)), 9).text == "막힘: 없는 팀임"
    assert service.apply_to_team(fresh, uid(fresh, no(5)), 1).status == "대기"
    assert service.apply_to_team(fresh, uid(fresh, no(5)), 2).text == "막힘: 결과를 기다리는 지원이 있음"
    assert count(fresh, "select count(*) from tf_mp_applications") == 2  # 막힌 지원은 기록하지 않음
    service.vote(fresh, uid(fresh, no(1)), no(5), "찬성")
    seat(fresh, 9, 1)
    seat(fresh, 10, 1)
    assert team_member_nos(fresh, 1) == [no(1), no(5), no(9), no(10)]
    assert service.apply_to_team(fresh, uid(fresh, no(11)), 1).text == "막힘: 팀이 꽉 참"
    assert service.close_recruitment(fresh, admin(fresh)).ok
    assert service.apply_to_team(fresh, uid(fresh, no(11)), 2).text == "막힘: 모집이 마감됨"


def test_apply_before_roster_is_blocked(pool):
    _, admin_id = service.login(pool, "admin", get_secret("ADMIN_PASSWORD"))
    with pool.connection() as conn:
        conn.execute("delete from tf_mp_settings where key = 'phase'")
    try:
        assert service.apply_to_team(pool, admin_id, 1).text == "막힘: 아직 명단이 올라오지 않음"
    finally:
        assert service.start_roster(pool, admin_id, (DATA / "중간.csv").read_bytes(), 4).ok


def test_close_is_admin_only_and_only_once(fresh):
    assert service.close_recruitment(fresh, uid(fresh, no(1))).text == "막힘: 관리자만 할 수 있음"
    first = service.close_recruitment(fresh, admin(fresh))
    assert first.status == "승인"
    assert service.close_recruitment(fresh, admin(fresh)).text == "막힘: 모집 중일 때만 마감할 수 있음"


def test_reset_clears_applications_and_votes(fresh):
    seat(fresh, 1, 1)
    service.apply_to_team(fresh, uid(fresh, no(5)), 1)
    service.vote(fresh, uid(fresh, no(1)), no(5), "찬성")
    _, admin_id = service.login(fresh, "admin", get_secret("ADMIN_PASSWORD"))
    assert service.start_roster(fresh, admin_id, (DATA / "중간.csv").read_bytes(), 4).ok
    assert count(fresh, "select count(*) from tf_mp_applications") == 0
    assert count(fresh, "select count(*) from tf_mp_votes") == 0
    assert count(fresh, "select count(*) from tf_mp_members") == 0


def run_together(calls):
    """호출 여러 개를 스레드로 동시에 보내 결과를 모음"""
    barrier = threading.Barrier(len(calls))
    results = [None] * len(calls)

    def worker(n, call):
        barrier.wait(timeout=10)
        results[n] = call()

    threads = [threading.Thread(target=worker, args=(n, c)) for n, c in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert all(r is not None for r in results), "스레드가 끝나지 않음"
    return results


def test_two_students_applying_to_the_same_empty_team_at_once(fresh):
    results = run_together([
        lambda: service.apply_to_team(fresh, uid(fresh, no(1)), 2),
        lambda: service.apply_to_team(fresh, uid(fresh, no(5)), 2),
    ])
    assert sorted(r.status for r in results) == ["대기", "승인"]
    assert len(team_member_nos(fresh, 2)) == 1


def test_one_student_applying_to_two_empty_teams_at_once(fresh):
    results = run_together([
        lambda: service.apply_to_team(fresh, uid(fresh, no(1)), 2),
        lambda: service.apply_to_team(fresh, uid(fresh, no(1)), 3),
    ])
    assert sorted(r.status for r in results) == ["막힘", "승인"]
    assert count(fresh, "select count(*) from tf_mp_members") == 1


def test_two_pending_applications_for_the_last_slot_are_decided_in_vote_order(fresh):
    # 팀1(학생1, 5, 10)의 마지막 정원에 학생9와 학생11이 대기 중이고, 학생10의 찬성 1표씩만 남음
    for i in (1, 5, 10):
        seat(fresh, i, 1)
    for applicant in (9, 11):
        assert service.apply_to_team(fresh, uid(fresh, no(applicant)), 1).status == "대기"
        for voter in (1, 5):
            assert service.vote(fresh, uid(fresh, no(voter)), no(applicant), "찬성").status == "대기"
    results = run_together([
        lambda: service.vote(fresh, uid(fresh, no(10)), no(9), "찬성"),
        lambda: service.vote(fresh, uid(fresh, no(10)), no(11), "찬성"),
    ])
    # 먼저 마지막 투표를 기록한 지원이 승인되고(투표가 끝난 순서), 나머지는 새 팀원의 투표를 더 받아야 하므로 대기임
    assert sorted(r.status for r in results) == ["대기", "승인"]
    approved, waiting = (9, 11) if results[0].status == "승인" else (11, 9)
    assert team_member_nos(fresh, 1) == [no(1), no(5), no(10), no(approved)]
    # 새 팀원이 찬성하면 마지막 투표 시점의 승인 직전 재검사에서 정원 초과로 거절됨
    last = service.vote(fresh, uid(fresh, no(approved)), no(waiting), "찬성")
    assert last.status == "거절" and "팀이 꽉 참" in last.message
    assert len(team_member_nos(fresh, 1)) == 4
