# 2026-10-31 13:02 KST
"""확정 단추(admin_confirm)는 배정안이 있고 AI 배정이 돌고 있지 않을 때만 눌려야 함

채점 프로그램(자동 채점/grade.js)은 눌러지는 확정 단추(button:not([disabled]))가 보이면 배정안이 왔다고 보고 곧바로 누름.
배정안이 없을 때나 AI 배정이 도는 동안에도 눌리면, 남은 학생이 배정되지 않은 채 확정되어 버림
"""
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import DATA, ROOT
from mp import ai, service
from mp.config import get_secret
from mp.db import make_pool
from test_assign_flow import seat

pytestmark = pytest.mark.skipif(
    not (get_secret("DATABASE_URL") and get_secret("ADMIN_PASSWORD")), reason="DATABASE_URL 또는 ADMIN_PASSWORD 없음"
)

APP = str(ROOT / "streamlit_app.py")


@pytest.fixture(scope="module")
def pool():
    p = make_pool(get_secret("DATABASE_URL"), max_size=3)
    service.ensure_admin(p, get_secret("ADMIN_PASSWORD"))
    yield p
    p.close()


def admin_id(pool):
    return service.find_user_id(pool, "admin")


def start_open(pool):
    assert service.start_roster(pool, admin_id(pool), (DATA / "쉬움.csv").read_bytes(), 3).ok
    for i, team in ((1, 1), (2, 2), (3, 3), (4, 1), (5, 2), (6, 3)):
        seat(pool, i, team)


def start_closed(pool):
    start_open(pool)
    assert service.close_recruitment(pool, admin_id(pool)).ok


def make_proposal(pool):
    prep = service.prepare_assignment(pool, admin_id(pool))
    assert prep.result is None
    assert service.generate_proposal(pool, prep, None, (), 0, ai.Progress()).ok
    assert service.load_proposal(pool)


def admin_app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.text_input(key="login_student_no").set_value("admin")
    at.text_input(key="login_password").set_value(get_secret("ADMIN_PASSWORD"))
    at.button(key="login_submit").click().run()
    assert not at.exception
    return at


def confirm_disabled(at):
    return at.button(key="admin_confirm").disabled


def test_confirm_is_disabled_before_the_recruitment_is_closed(pool):
    start_open(pool)
    assert confirm_disabled(admin_app()) is True


def test_confirm_is_disabled_when_closed_but_there_is_no_proposal_yet(pool):
    start_closed(pool)
    assert service.load_proposal(pool) is None
    assert confirm_disabled(admin_app()) is True


def test_confirm_is_enabled_once_a_proposal_exists(pool):
    start_closed(pool)
    make_proposal(pool)
    assert confirm_disabled(admin_app()) is False


def test_confirm_is_disabled_while_the_ai_assignment_is_running(pool, monkeypatch):
    # 배정안이 이미 있는 상태에서 AI 배정을 다시 누른 직후(배정이 도는 동안)의 화면을 멈춰서 봄:
    # 실행을 끝내는 st.rerun()을 st.stop()으로 바꿔 두면 배정이 도는 동안 그려진 단추가 그대로 남음
    start_closed(pool)
    make_proposal(pool)
    at = admin_app()
    assert confirm_disabled(at) is False
    monkeypatch.setattr(service, "prepare_assignment", lambda pool_, user_id: service.Prep(service.Result("막힘", "시험")))
    monkeypatch.setattr(st, "rerun", st.stop)
    at.session_state["assigning"] = True
    at.run()
    assert not at.exception
    assert at.button(key="admin_assign").disabled is True  # 배정이 도는 화면임을 확인함
    assert confirm_disabled(at) is True


def test_confirm_is_disabled_again_after_the_assignment_is_confirmed(pool):
    start_closed(pool)
    make_proposal(pool)
    at = admin_app()
    at.button(key="admin_confirm").click().run()
    assert not at.exception
    assert service.load_view(pool)["phase"] == "confirmed"
    assert confirm_disabled(at) is True
