# 2026-10-31 11:14 KST
"""연습 시나리오 페이지(pages/practice.py)의 화면 시험(PRD_step4 8장 S-5, S-7, P-2, N-1). Streamlit AppTest를 씀

실제 DB를 읽는 로그인 칸 시험이 아니라, 세션 상태를 미리 채워 화면이 저장한 기록만 읽는지를 확인함
"""
import pytest
from streamlit.testing.v1 import AppTest

from conftest import DATA, ROOT
from mp import practice, practice_run
from mp.config import get_secret

pytestmark = pytest.mark.skipif(
    not (get_secret("DATABASE_URL") and get_secret("ADMIN_PASSWORD")), reason="DATABASE_URL 또는 ADMIN_PASSWORD 없음"
)

PAGE = str(ROOT / "pages" / "practice.py")
ADMIN = {"id": 1, "student_no": "admin", "name": "관리자", "is_admin": True}
STUDENT = {"id": 2, "student_no": "s1", "name": "학생", "is_admin": False}
WARNING = "채점 프로그램이 이 앱을 조작하는 동안에는 이 페이지를 쓰지 마십시오."


def person(no, name, main="기획자"):
    return {"id": hash(no) % 1000, "student_no": no, "name": name, "main_role": main, "sub_roles": []}


def view(members_of_team1=(), unassigned=(), phase="open"):
    return {"phase": phase, "unassigned": list(unassigned), "teams": [
        {"id": 1, "team_no": 1, "name": "팀1", "members": list(members_of_team1), "pending": []},
        {"id": 2, "team_no": 2, "name": "팀2", "members": [], "pending": []}]}


def record(before, after, status="승인", action="지원", message="테스트"):
    return {"rows": [{"action": action, "status": status, "message": message, "skipped": False}],
            "before": before, "after": after, "after_db": after, "started_at": "2026-10-31 12:00:00"}


def units():
    text = ("step,action,actor,team_no,target,choice,expected,note\n"
            "1,지원,a1,1,,,승인,첫째 지원\n2,지원,b1,2,,,승인,둘째 지원\n3,마감,,,,,승인,\n3,배정,,,,,승인,\n")
    return practice.split_units(practice.parse_steps(text.encode("utf-8")))


def page(**state):
    at = AppTest.from_file(PAGE, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    return at


def texts(at, key):
    box = at.get_by_key(key)
    return " ".join(str(e.value) for kind in ("markdown", "text", "caption") for e in getattr(box, kind))


def run_buttons(at):
    return [b.key for b in at.button if b.key and b.key.startswith("practice_run_")]


# ---- N-1: 안내 문구 ----

def test_the_warning_line_is_shown_even_before_login():
    at = page()
    at.run()
    assert not at.exception
    assert any(WARNING in str(w.value) for w in at.warning)
    assert any("시나리오 시작" in str(w.value) and "모두 지웁니다" in str(w.value) for w in at.warning)


def test_readme_has_the_same_notice_in_one_line():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if "채점 프로그램" in l and "연습 시나리오" in l and "쓰지" in l]
    assert len(lines) == 1


# ---- P-2: 화면 권한 ----

def test_no_run_buttons_before_login_or_for_a_student_account():
    at = page()
    at.run()
    assert not at.exception and run_buttons(at) == []
    at = page(practice_user=STUDENT, practice_units=units(), practice_records={})
    at.run()
    assert not at.exception and run_buttons(at) == []
    assert any("관리자" in str(e.value) for kind in ("markdown", "text", "warning", "error", "info") for e in getattr(at, kind))


# ---- S-7: 기록 없음 ----

def test_a_fresh_session_without_units_offers_no_run_button_and_says_there_is_no_record():
    at = page(practice_user=ADMIN)
    at.run()
    assert not at.exception
    assert run_buttons(at) == []
    assert any("저장한 기록이 없음" in str(e.value) for kind in ("markdown", "text", "info") for e in getattr(at, kind))


# ---- S-5: 이미 실행한 하위 단계는 다시 실행하지 않고 저장한 기록을 보여 줌 ----

def stub_run_unit(monkeypatch, calls):
    def fake(pool, admin_id, actions, ai_plan=None):
        calls.append([a.action for a in actions])
        v = view([person("a1", "학생A")])
        return record(v, v)
    monkeypatch.setattr(practice_run, "run_unit", fake)


def test_pressing_a_finished_unit_shows_the_saved_before_and_after_without_running(monkeypatch):
    calls = []
    stub_run_unit(monkeypatch, calls)
    us = units()
    before1, after1 = view(), view([person("a1", "학생이름하나")])
    records = {"1": record(before1, after1), "2": record(after1, view([person("a1", "학생이름하나"), person("b1", "학생이름둘")]))}
    at = page(practice_user=ADMIN, practice_units=us, practice_records=records)
    at.run()
    assert not at.exception
    assert [b.label for b in at.button if b.key in ("practice_run_1", "practice_run_2", "practice_run_3_1")] == ["보기", "보기", "실행"]
    at.button(key="practice_run_1").click().run()
    assert not at.exception
    assert calls == []  # 서비스 함수(실행기)를 부르지 않음
    assert "학생이름하나" in texts(at, "practice_after")
    assert "학생이름하나" not in texts(at, "practice_before")
    # 앞 하위 단계로 되돌아가 보기: 다른 단계를 눌러도 저장한 값이 그대로 보임
    at.button(key="practice_run_2").click().run()
    assert "학생이름둘" in texts(at, "practice_after")
    at.button(key="practice_run_1").click().run()
    assert "학생이름하나" in texts(at, "practice_after") and calls == []


def test_a_waiting_unit_has_a_disabled_button_and_does_not_run(monkeypatch):
    calls = []
    stub_run_unit(monkeypatch, calls)
    at = page(practice_user=ADMIN, practice_units=units(), practice_records={})
    at.run()
    buttons = {b.key: b for b in at.button if b.key and b.key.startswith("practice_run_")}
    assert buttons["practice_run_1"].disabled is False and buttons["practice_run_1"].label == "실행"
    assert buttons["practice_run_2"].disabled is True and buttons["practice_run_2"].label == "대기"
    assert calls == []


def test_a_pending_request_runs_once_and_is_not_repeated_on_the_next_run(monkeypatch):
    calls = []
    stub_run_unit(monkeypatch, calls)
    at = page(practice_user=ADMIN, practice_units=units(), practice_records={}, practice_pending="1")
    at.run()
    assert not at.exception and len(calls) == 1
    at.run()
    assert len(calls) == 1  # 기록이 생겼고 요청은 지워졌으므로 다시 실행하지 않음
    assert "1" in at.session_state["practice_records"]


# ---- 모델 호출 토글의 표시 ----

def test_the_assign_row_shows_that_turning_the_toggle_on_calls_real_models(monkeypatch):
    monkeypatch.setattr("mp.service.count_ai_calls_today", lambda pool: 5)
    records = {"1": record(view(), view()), "2": record(view(), view()),
               "3-1": record(view(), view(), action="마감")}
    at = page(practice_user=ADMIN, practice_units=units(), practice_records=records)
    at.run()
    assert not at.exception
    assert "앱이 직접 배정" in at.button(key="practice_run_3_2").label
    assert any("오늘" in str(e.value) and "5" in str(e.value) for kind in ("markdown", "caption", "text") for e in getattr(at, kind))
    at.toggle(key="practice_ai_on").set_value(True).run()
    assert not at.exception
    assert "실제 모델 호출" in at.button(key="practice_run_3_2").label
    assert any("실제 모델을 부름" in str(e.value) for e in at.markdown)
