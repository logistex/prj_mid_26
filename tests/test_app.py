# 2026-10-30 21:58 KST
"""화면 시험(PRD_step1 8장 시험 5, 6, 9, 10). Streamlit AppTest로 앱을 실행해 key로 요소를 찾음

실제 Supabase DB의 tf_mp_ 테이블을 씀. 비밀 값은 출력하지 않음
"""
import pytest
from streamlit.testing.v1 import AppTest

from conftest import DATA, ROOT
from mp import service
from mp.config import get_secret
from mp.db import make_pool

pytestmark = pytest.mark.skipif(
    not (get_secret("DATABASE_URL") and get_secret("ADMIN_PASSWORD")), reason="DATABASE_URL 또는 ADMIN_PASSWORD 없음"
)

APP = str(ROOT / "streamlit_app.py")


@pytest.fixture(scope="module", autouse=True)
def roster():
    pool = make_pool(get_secret("DATABASE_URL"), max_size=1)
    service.ensure_admin(pool, get_secret("ADMIN_PASSWORD"))
    _, admin_id = service.login(pool, "admin", get_secret("ADMIN_PASSWORD"))
    assert service.start_roster(pool, admin_id, (DATA / "쉬움.csv").read_bytes(), 3).ok
    pool.close()


def new_app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception
    return at


def login(at, student_no, password):
    at.text_input(key="login_student_no").set_value(student_no)
    at.text_input(key="login_password").set_value(password)
    at.button(key="login_submit").click()
    at.run()
    assert not at.exception


def result_text(at):
    return " ".join(e.value for e in at.text if e.value.startswith(("승인", "대기", "거절", "막힘")))


def all_text(at):
    parts = []
    for kind in ("text", "markdown", "error", "info", "warning", "title", "subheader"):
        parts += [str(e.value) for e in getattr(at, kind)]
    return "\n".join(parts)


def test_login_screen_has_the_required_keys():
    at = new_app()
    at.text_input(key="login_student_no")
    at.text_input(key="login_password")
    at.button(key="login_submit")
    assert "로그인하지 않음" in all_text(at)


def test_wrong_password_is_blocked():
    at = new_app()
    login(at, "2026101", "9999")
    assert result_text(at).startswith("막힘")
    assert "로그인하지 않음" in all_text(at)


def test_student_logs_in_with_default_password():
    at = new_app()
    login(at, "2026101", "1234")
    assert result_text(at).startswith("승인")
    assert "학생1(PL;RW) (2026101)" in all_text(at)
    assert "아직 팀이 없음" in all_text(at)
    for n in (1, 2, 3):
        at.get_by_key(f"team_{n}")
    with pytest.raises(Exception):
        at.get_by_key("admin_start")  # 학생 화면에는 관리자 단추가 없음


def test_admin_screen_has_the_required_keys_and_reset_works():
    at = new_app()
    login(at, "admin", get_secret("ADMIN_PASSWORD"))
    assert "관리자" in all_text(at)
    at.get_by_key("admin_roster_file")
    at.number_input(key="admin_team_count")
    at.button(key="admin_start")
    at.get_by_key("unassigned")
    at.get_by_key("whoami")
    at.get_by_key("result")


def test_secrets_never_appear_on_screen():
    for who in (("2026101", "1234"), ("admin", get_secret("ADMIN_PASSWORD"))):
        at = new_app()
        login(at, *who)
        text = all_text(at)
        assert "postgresql://" not in text
        assert "sk-or-" not in text
        for key in ("DATABASE_URL", "OPENROUTER_API_KEY", "ADMIN_PASSWORD"):
            value = get_secret(key)
            assert not (value and len(value) >= 6 and value in text)
