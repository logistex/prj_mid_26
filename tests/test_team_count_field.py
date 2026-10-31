# 2026-10-31 19:52 KST
"""관리자 화면의 "팀 수" 칸은 DB에 있는 지금 팀 수를 보여야 함(README 7항 문제 1)

처음값을 3으로 고정해 두면, 팀 수 칸을 직접 바꾸지 않은 세션(다시 로그인, 새로고침, 다른 곳에서 만든 상태)은 DB에 팀이 4개 있어도
3을 보여 줌. 그 상태에서 명단 CSV를 올려 "명단으로 처음 상태 만들기"를 누르면 팀 3개로 다시 만들어지고 지원과 투표가 지워짐
"""
import pytest
from streamlit.testing.v1 import AppTest

from conftest import DATA, ROOT, plain
from mp import service
from mp.config import get_secret
from mp.db import make_pool

pytestmark = pytest.mark.skipif(
    not (get_secret("DATABASE_URL") and get_secret("ADMIN_PASSWORD")), reason="DATABASE_URL 또는 ADMIN_PASSWORD 없음"
)

APP = str(ROOT / "streamlit_app.py")
KEY = "admin_team_count"


@pytest.fixture(scope="module")
def pool():
    p = make_pool(get_secret("DATABASE_URL"), max_size=3)
    service.ensure_admin(p, get_secret("ADMIN_PASSWORD"))
    yield p
    p.close()


def admin_id(pool):
    return service.find_user_id(pool, "admin")


def start(pool, csv, teams):
    assert service.start_roster(pool, admin_id(pool), (DATA / csv).read_bytes(), teams).ok


def admin_app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.text_input(key="login_student_no").set_value("admin")
    at.text_input(key="login_password").set_value(get_secret("ADMIN_PASSWORD"))
    at.button(key="login_submit").click().run()
    assert not at.exception
    return at


def shown(at):
    return at.number_input(key=KEY).value


def db_team_count(pool):
    return len(service.load_view(pool)["teams"])


def test_a_new_admin_session_shows_the_team_count_in_the_db(pool):
    start(pool, "중간.csv", 4)
    assert shown(admin_app()) == 4


def test_the_team_count_is_still_the_one_in_the_db_after_closing_recruitment(pool):
    # 부록 2(중간)는 팀 4개로 시작해 9단계에서 모집을 마감함
    start(pool, "중간.csv", 4)
    at = admin_app()
    at.button(key="admin_close").click().run()
    assert not at.exception
    assert service.load_view(pool)["phase"] == "closed"
    assert shown(at) == 4


def test_a_value_the_admin_typed_is_kept_when_the_screen_refreshes(pool):
    start(pool, "중간.csv", 4)
    at = admin_app()
    at.number_input(key=KEY).set_value(6).run()
    at.run()
    assert shown(at) == 6
    assert db_team_count(pool) == 4


def test_the_field_goes_back_to_the_db_value_after_one_run_that_could_not_draw_it(pool, monkeypatch):
    # DB 오류 등으로 화면을 그리다 멈추면 위젯이 그려지지 않아 Streamlit이 위젯 상태를 지움(문서: 그려지지 않은 위젯은 상태가 삭제됨)
    start(pool, "중간.csv", 4)
    at = admin_app()
    real = service.load_page

    def broken(pool_, user_id):
        raise RuntimeError("시험용 DB 오류")

    monkeypatch.setattr(service, "load_page", broken)
    at.run()
    assert not at.exception
    monkeypatch.setattr(service, "load_page", real)
    at.run()
    assert shown(at) == 4


def test_the_field_follows_the_db_when_the_team_count_changes_in_the_same_session(pool):
    start(pool, "중간.csv", 4)
    at = admin_app()
    assert shown(at) == 4
    start(pool, "중간.csv", 3)  # 연습 시나리오 탭의 "시나리오 시작"처럼 같은 세션 안에서 팀 수가 바뀜
    at.run()
    assert shown(at) == 3


def test_pressing_start_without_a_roster_file_is_blocked_and_keeps_the_teams(pool):
    start(pool, "중간.csv", 4)
    at = admin_app()
    at.button(key="admin_start").click().run()
    assert not at.exception
    assert plain(at.get_by_key("result").markdown[0].value).startswith("막힘")
    assert db_team_count(pool) == 4


def test_the_field_is_3_while_the_db_has_no_team(pool, monkeypatch):
    start(pool, "중간.csv", 4)
    real = service.load_page

    def no_teams(pool_, user_id):
        user, view = real(pool_, user_id)
        return user, dict(view, teams=[])

    monkeypatch.setattr(service, "load_page", no_teams)
    assert shown(admin_app()) == 3
