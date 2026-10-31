# 2026-10-31 13:08 KST
"""기본 화면 안의 "시나리오 실행" 탭 시험(PRD_step4 4.1절, 4.2절). 관리자에게만 탭 2개가 보이고, 학생 화면은 그대로이며,
"팀 편성" 탭이 처음 열려서 공고 2.7절의 key가 첫 화면에 모두 있고, "시나리오 실행" 탭의 코드는 그 탭이 열렸을 때만 실행됨

실제 Supabase DB를 쓰고, 실행기(practice_run.run_unit)는 서비스 함수를 부르지 않는 대역으로 바꿔 화면만 시험함
"""
import pytest
from streamlit.testing.v1 import AppTest

from conftest import DATA, ROOT
from mp import practice, practice_run, practice_view, service
from mp.config import get_secret
from mp.db import make_pool

pytestmark = pytest.mark.skipif(
    not (get_secret("DATABASE_URL") and get_secret("ADMIN_PASSWORD")), reason="DATABASE_URL 또는 ADMIN_PASSWORD 없음"
)

APP = str(ROOT / "streamlit_app.py")
TAB_KEY = "main_tabs"
TEAM_TAB, PRACTICE_TAB = "팀 편성", "시나리오 실행"
WARNING = "채점하는 동안에는 이 탭을 쓰지 마십시오(채점 프로그램을 돌릴 때와 손으로 조작할 때 모두)."
FIRST_SCREEN_KEYS = ("whoami", "result", "logout", "unassigned", "admin_roster_file", "admin_team_count", "admin_start",
                     "admin_close", "admin_assign", "assign_status", "proposal", "admin_confirm", "team_1", "team_2", "team_3")


@pytest.fixture(scope="module")
def pool():
    p = make_pool(get_secret("DATABASE_URL"), max_size=3)
    service.ensure_admin(p, get_secret("ADMIN_PASSWORD"))
    assert service.start_roster(p, service.find_user_id(p, "admin"), (DATA / "쉬움.csv").read_bytes(), 3).ok
    yield p
    p.close()


def login(student_no, password):
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.text_input(key="login_student_no").set_value(student_no)
    at.text_input(key="login_password").set_value(password)
    at.button(key="login_submit").click().run()
    assert not at.exception
    return at


def admin_app():
    return login("admin", get_secret("ADMIN_PASSWORD"))


def present(at, key):
    try:
        at.get_by_key(key)
        return True
    except Exception:
        return False


# ---- 탭 ----

def test_the_admin_sees_two_tabs_and_the_team_tab_comes_first(pool):
    at = admin_app()
    assert [t.label for t in at.tabs] == [TEAM_TAB, PRACTICE_TAB]


def test_a_student_sees_no_tabs_and_the_same_screen_as_before(pool):
    at = login("2026101", "1234")
    assert len(at.tabs) == 0
    assert present(at, "whoami") and present(at, "team_1") and not present(at, "admin_start")


def test_every_key_of_the_first_screen_is_there_without_opening_any_tab(pool):
    at = admin_app()
    missing = [k for k in FIRST_SCREEN_KEYS if not present(at, k)]
    assert missing == []
    assert any("관리자 (admin)" in e.value for e in at.get_by_key("whoami").text)


def test_the_first_screen_keys_that_belong_to_the_team_screen_are_inside_the_first_tab(pool):
    at = admin_app()
    first = at.tabs[0]
    inside = [k for k in ("result", "unassigned", "admin_roster_file", "admin_start", "admin_close", "admin_assign",
                          "assign_status", "proposal", "admin_confirm", "team_1") if k and _has(first, k)]
    assert inside == ["result", "unassigned", "admin_roster_file", "admin_start", "admin_close", "admin_assign",
                      "assign_status", "proposal", "admin_confirm", "team_1"]


def _has(block, key):
    try:
        block.get_by_key(key)
        return True
    except Exception:
        return False


# ---- 시나리오 실행 탭은 열렸을 때만 실행됨 ----

def test_the_practice_tab_code_runs_only_while_that_tab_is_open(pool, monkeypatch):
    calls = []
    monkeypatch.setattr(practice_view, "render", lambda pool_, user: calls.append(user["is_admin"]))
    at = admin_app()
    assert calls == []
    at.session_state[TAB_KEY] = PRACTICE_TAB
    at.run()
    assert not at.exception and calls == [True]
    at.session_state[TAB_KEY] = TEAM_TAB
    at.run()
    assert calls == [True]


def test_a_student_never_runs_the_practice_tab_code(pool, monkeypatch):
    calls = []
    monkeypatch.setattr(practice_view, "render", lambda pool_, user: calls.append(1))
    at = login("2026101", "1234")
    at.session_state[TAB_KEY] = PRACTICE_TAB
    at.run()
    assert not at.exception and calls == []


# ---- 시나리오 실행 탭의 내용(저장한 기록 보기 등) ----

def person(no, name, main="기획자"):
    return {"id": hash(no) % 1000, "student_no": no, "name": name, "main_role": main, "sub_roles": []}


def view(team1=(), unassigned=(), phase="open"):
    return {"phase": phase, "unassigned": list(unassigned), "teams": [
        {"id": 1, "team_no": 1, "name": "팀1", "members": list(team1), "pending": []},
        {"id": 2, "team_no": 2, "name": "팀2", "members": [], "pending": []}]}


def record(before, after, status="승인", action="지원"):
    return {"rows": [{"action": action, "status": status, "message": "테스트", "skipped": False}],
            "before": before, "after": after, "after_db": after, "started_at": "2026-10-31 12:00:00"}


def units():
    text = ("step,action,actor,team_no,target,choice,expected,note\n"
            "1,지원,a1,1,,,승인,첫째 지원\n2,지원,b1,2,,,승인,둘째 지원\n3,마감,,,,,승인,\n3,배정,,,,,승인,\n")
    return practice.split_units(practice.parse_steps(text.encode("utf-8")))


def practice_app(**state):
    at = admin_app()
    for k, v in state.items():
        at.session_state[k] = v
    at.session_state[TAB_KEY] = PRACTICE_TAB
    at.run()
    assert not at.exception
    return at


def texts(at, key):
    box = at.get_by_key(key)
    return " ".join(str(e.value) for kind in ("markdown", "text", "caption") for e in getattr(box, kind))


def run_buttons(at):
    return [b.key for b in at.button if b.key and b.key.startswith("practice_run_")]


def stub_run_unit(monkeypatch, calls):
    def fake(pool, admin_id, actions, ai_plan=None):
        calls.append([a.action for a in actions])
        v = view([person("a1", "학생A")])
        return record(v, v)
    monkeypatch.setattr(practice_run, "run_unit", fake)


def test_the_warning_is_at_the_top_of_the_practice_tab(pool):
    at = practice_app()
    assert any(WARNING in str(w.value) and "모두 지웁니다" in str(w.value) for w in at.warning)


def test_a_fresh_session_has_no_run_button_and_says_there_is_no_record(pool):
    at = practice_app()
    assert run_buttons(at) == []
    assert any("저장한 기록이 없음" in str(e.value) for kind in ("markdown", "text", "info") for e in getattr(at, kind))


def test_pressing_a_finished_unit_shows_the_saved_before_and_after_without_running(pool, monkeypatch):
    calls = []
    stub_run_unit(monkeypatch, calls)
    before1, after1 = view(), view([person("a1", "학생이름하나")])
    records = {"1": record(before1, after1),
               "2": record(after1, view([person("a1", "학생이름하나"), person("b1", "학생이름둘")]))}
    at = practice_app(practice_units=units(), practice_records=records)
    assert [b.label for b in at.button if b.key in ("practice_run_1", "practice_run_2", "practice_run_3_1")] == ["보기", "보기", "실행"]
    at.button(key="practice_run_1").click().run()
    assert not at.exception and calls == []
    assert "학생이름하나" in texts(at, "practice_after") and "학생이름하나" not in texts(at, "practice_before")
    at.button(key="practice_run_2").click().run()
    assert "학생이름둘" in texts(at, "practice_after")
    at.button(key="practice_run_1").click().run()
    assert "학생이름하나" in texts(at, "practice_after") and calls == []


def test_a_waiting_unit_has_a_disabled_button_and_does_not_run(pool, monkeypatch):
    calls = []
    stub_run_unit(monkeypatch, calls)
    at = practice_app(practice_units=units(), practice_records={})
    buttons = {b.key: b for b in at.button if b.key and b.key.startswith("practice_run_")}
    assert buttons["practice_run_1"].disabled is False and buttons["practice_run_1"].label == "실행"
    assert buttons["practice_run_2"].disabled is True and buttons["practice_run_2"].label == "대기"
    assert calls == []


def test_a_pending_request_runs_once_and_is_not_repeated_on_the_next_run(pool, monkeypatch):
    calls = []
    stub_run_unit(monkeypatch, calls)
    at = practice_app(practice_units=units(), practice_records={}, practice_pending="1")
    assert len(calls) == 1
    at.run()
    assert len(calls) == 1
    assert "1" in at.session_state["practice_records"]


def test_the_assign_row_shows_that_turning_the_toggle_on_calls_real_models(pool, monkeypatch):
    monkeypatch.setattr(service, "count_ai_calls_today", lambda pool_: 5)
    records = {"1": record(view(), view()), "2": record(view(), view()), "3-1": record(view(), view(), action="마감")}
    at = practice_app(practice_units=units(), practice_records=records)
    assert "앱이 직접 배정" in at.button(key="practice_run_3_2").label
    assert any("오늘" in str(e.value) and "5" in str(e.value) for kind in ("markdown", "caption", "text") for e in getattr(at, kind))
    at.toggle(key="practice_ai_on").set_value(True).run()
    assert not at.exception
    assert "실제 모델 호출" in at.button(key="practice_run_3_2").label
    assert any("실제 모델을 부름" in str(e.value) for e in at.markdown)


def test_logging_out_clears_the_saved_practice_records(pool):
    at = practice_app(practice_units=units(), practice_records={"1": record(view(), view())})
    assert "practice_records" in at.session_state
    at.button(key="logout").click().run()
    assert not at.exception
    assert "practice_units" not in at.session_state and "practice_records" not in at.session_state


def test_readme_has_the_same_notice_in_one_line():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if "채점 프로그램" in l and "연습 시나리오" in l and "쓰지" in l]
    assert len(lines) == 1
