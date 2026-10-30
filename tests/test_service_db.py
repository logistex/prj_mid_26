# 2026-10-30 21:58 KST
"""DB 제약과 서비스 시험(PRD_step1 8장 시험 1, 2, 3, 6, 7, 8). 실제 Supabase DB의 tf_mp_ 테이블을 씀

이 시험은 tf_mp_ 테이블의 내용을 지우고 쉬움.csv로 다시 채움. 비밀 값은 출력하지 않음
"""
import subprocess
import sys
import threading

import psycopg
import pytest
from psycopg import errors

from conftest import DATA, ROOT
from mp import service
from mp.config import get_secret
from mp.db import make_pool

pytestmark = pytest.mark.skipif(
    not (get_secret("DATABASE_URL") and get_secret("ADMIN_PASSWORD")), reason="DATABASE_URL 또는 ADMIN_PASSWORD 없음"
)

ROSTER = (DATA / "쉬움.csv").read_bytes()


@pytest.fixture(scope="module")
def pool():
    p = make_pool(get_secret("DATABASE_URL"))
    service.ensure_admin(p, get_secret("ADMIN_PASSWORD"))
    yield p
    p.close()


@pytest.fixture
def admin_id(pool):
    res, uid = service.login(pool, "admin", get_secret("ADMIN_PASSWORD"))
    assert res.ok
    return uid


@pytest.fixture
def fresh(pool, admin_id):
    res = service.start_roster(pool, admin_id, ROSTER, 3)
    assert res.ok, res.text
    return pool


def count(pool, sql):
    with pool.connection() as conn:
        return conn.execute(sql).fetchone()[0]


def test_schema_applies_twice_without_error():
    for _ in range(2):
        out = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "apply_schema.py")], capture_output=True, text=True
        )
        assert out.returncode == 0
        assert "스키마 적용됨" in out.stdout


def test_ensure_admin_is_idempotent(pool):
    service.ensure_admin(pool, get_secret("ADMIN_PASSWORD"))
    assert count(pool, "select count(*) from tf_mp_students where student_no = 'admin'") == 1


def test_ensure_admin_updates_changed_password_and_restores(pool):
    # 관리자 비밀번호가 바뀌면 해시만 갱신함. 시험 뒤에는 원래 값으로 되돌림
    service.ensure_admin(pool, "임시-시험용-비밀번호")
    assert service.login(pool, "admin", "임시-시험용-비밀번호")[0].ok
    service.ensure_admin(pool, get_secret("ADMIN_PASSWORD"))
    assert service.login(pool, "admin", get_secret("ADMIN_PASSWORD"))[0].ok
    assert not service.login(pool, "admin", "임시-시험용-비밀번호")[0].ok


def test_start_roster_creates_students_and_teams(fresh):
    view = service.load_view(fresh)
    assert view["phase"] == "open"
    assert [t["name"] for t in view["teams"]] == ["팀1", "팀2", "팀3"]
    assert all(t["members"] == [] for t in view["teams"])
    assert len(view["unassigned"]) == 8
    assert count(fresh, "select count(*) from tf_mp_students where student_no = 'admin'") == 1


def test_start_roster_twice_keeps_admin_and_resets(pool, admin_id):
    for _ in range(2):
        assert service.start_roster(pool, admin_id, ROSTER, 4).ok
    assert len(service.load_view(pool)["teams"]) == 4
    assert count(pool, "select count(*) from tf_mp_students where not is_admin") == 8
    assert count(pool, "select count(*) from tf_mp_students where is_admin") == 1


def test_student_passwords_are_hashed(fresh):
    with fresh.connection() as conn:
        hashes = [r[0] for r in conn.execute("select password_hash from tf_mp_students").fetchall()]
    assert all(h.startswith("$2") for h in hashes)
    assert not any("1234" == h for h in hashes)


def test_student_login_with_default_password(fresh):
    res, uid = service.login(fresh, "2026101", "1234")
    assert res.ok and uid is not None
    assert service.get_user(fresh, uid)["name"] == "학생1(PL;RW)"


def test_wrong_password_is_blocked_and_message_does_not_tell_which_is_wrong(fresh):
    wrong_pw, uid1 = service.login(fresh, "2026101", "9999")
    unknown, uid2 = service.login(fresh, "2099999", "1234")
    assert uid1 is None and uid2 is None
    assert wrong_pw == unknown
    assert wrong_pw.text.startswith("막힘")


def test_student_number_alone_does_not_log_in(fresh):
    assert service.login(fresh, "2026101", "")[1] is None
    assert service.login(fresh, "", "1234")[1] is None


def test_too_long_password_is_blocked(fresh):
    assert service.login(fresh, "2026101", "가" * 40)[1] is None


def test_student_cannot_start_roster(fresh):
    _, student_id = service.login(fresh, "2026101", "1234")
    before = count(fresh, "select count(*) from tf_mp_students")
    res = service.start_roster(fresh, student_id, ROSTER, 9)
    assert res.text == "막힘: 관리자만 할 수 있음"
    assert count(fresh, "select count(*) from tf_mp_students") == before
    assert count(fresh, "select count(*) from tf_mp_teams") == 3


def test_invalid_roster_leaves_previous_state(fresh, admin_id):
    bad = "student_no,name,main_role,sub_roles\n1,가,마법사,\n".encode("utf-8")
    res = service.start_roster(fresh, admin_id, bad, 5)
    assert res.status == "막힘" and "역할 값이 올바르지 않음" in res.message
    assert count(fresh, "select count(*) from tf_mp_students where not is_admin") == 8
    assert count(fresh, "select count(*) from tf_mp_teams") == 3


def test_missing_file_and_bad_team_count_are_blocked(fresh, admin_id):
    assert service.start_roster(fresh, admin_id, None, 3).text == "막힘: 명단 CSV 파일을 올리지 않음"
    assert service.start_roster(fresh, admin_id, ROSTER, 0).status == "막힘"
    assert service.start_roster(fresh, admin_id, ROSTER, None).status == "막힘"


def ids(pool):
    with pool.connection() as conn:
        teams = [r[0] for r in conn.execute("select id from tf_mp_teams order by team_no").fetchall()]
        students = [
            r[0] for r in conn.execute("select id from tf_mp_students where not is_admin order by student_no").fetchall()
        ]
    return teams, students


def test_constraints_reject_bad_rows(fresh):
    teams, students = ids(fresh)
    t1, t2 = teams[0], teams[1]
    s1, s2 = students[0], students[1]

    with pytest.raises(errors.CheckViolation):  # 5번째 정원
        with fresh.connection() as c:
            c.execute("insert into tf_mp_members (team_id, slot_no, student_id) values (%s, 5, %s)", (t1, s1))
    with pytest.raises(errors.UniqueViolation):  # 한 학생이 2개 팀에 소속
        with fresh.connection() as c:
            c.execute("insert into tf_mp_members (team_id, slot_no, student_id) values (%s, 1, %s)", (t1, s1))
            c.execute("insert into tf_mp_members (team_id, slot_no, student_id) values (%s, 1, %s)", (t2, s1))
    with pytest.raises(errors.UniqueViolation):  # 같은 정원에 2명
        with fresh.connection() as c:
            c.execute("insert into tf_mp_members (team_id, slot_no, student_id) values (%s, 1, %s)", (t1, s1))
            c.execute("insert into tf_mp_members (team_id, slot_no, student_id) values (%s, 1, %s)", (t1, s2))
    with pytest.raises(errors.CheckViolation):  # 6개 역할 밖의 값
        with fresh.connection() as c:
            c.execute(
                "insert into tf_mp_students (student_no, name, main_role, password_hash) values ('x1','가','마법사','h')"
            )
    with pytest.raises(errors.CheckViolation):  # 보조 역할의 값
        with fresh.connection() as c:
            c.execute("insert into tf_mp_student_sub_roles (student_id, role) values (%s, '마법사')", (s1,))
    with pytest.raises(errors.UniqueViolation):  # 학번 중복
        with fresh.connection() as c:
            c.execute(
                "insert into tf_mp_students (student_no, name, main_role, password_hash) values ('2026101','가','테스터','h')"
            )
    with pytest.raises(errors.CheckViolation):  # 관리자에게 역할이 있음
        with fresh.connection() as c:
            c.execute(
                "insert into tf_mp_students (student_no, name, main_role, password_hash, is_admin)"
                " values ('x2','가','테스터','h', true)"
            )
    with pytest.raises(errors.CheckViolation):  # 학생에게 역할이 없음
        with fresh.connection() as c:
            c.execute("insert into tf_mp_students (student_no, name, password_hash) values ('x3','가','h')")
    assert count(fresh, "select count(*) from tf_mp_members") == 0


def test_two_inserts_for_the_last_slot_only_one_succeeds(fresh):
    teams, students = ids(fresh)
    barrier = threading.Barrier(2)
    outcomes = []

    def worker(student_id):
        try:
            with fresh.connection() as c:
                barrier.wait(timeout=10)
                c.execute(
                    "insert into tf_mp_members (team_id, slot_no, student_id) values (%s, 4, %s)",
                    (teams[0], student_id),
                )
            outcomes.append("성공")
        except psycopg.errors.UniqueViolation:
            outcomes.append("거부")

    threads = [threading.Thread(target=worker, args=(s,)) for s in students[:2]]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(outcomes) == ["거부", "성공"]
    assert count(fresh, "select count(*) from tf_mp_members where slot_no = 4") == 1


def test_restore_practice_state(pool, admin_id):
    assert service.start_roster(pool, admin_id, ROSTER, 3).ok
