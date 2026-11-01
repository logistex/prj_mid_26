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


def screen_text(at):
    return " ".join(str(e.value) for kind in ("markdown", "subheader", "caption", "info") for e in getattr(at, kind))


def board_html(at):
    """판(st.html)의 HTML. 탭 위의 CSS 요소는 뺌"""
    return " ".join(e.value for e in at.html if "pb-grid" in e.value)


def step_buttons(at):
    """누를 수 있는 시간 줄 칸: 실행했고 지금 오른쪽에 보이지 않는 단계만 단추임"""
    return {b.key: b for b in at.button if b.key and b.key.startswith("practice_step_")}


def timeline_html(at):
    """눌러지지 않는 시간 줄 칸(지금 보이는 단계, 아직 실행하지 않은 단계)의 HTML"""
    return " ".join(e.value for e in at.html if "pv-card" in e.value)


def run_label(at):
    return at.button(key="practice_run_next").label


def stub_run_unit(monkeypatch, calls):
    def fake(pool, admin_id, actions, ai_plan=None):
        calls.append([a.action for a in actions])
        v = view([person("a1", "학생A")])
        return record(v, v)
    monkeypatch.setattr(practice_run, "run_unit", fake)


def two_done():
    before1, after1 = view(unassigned=[person("a1", "학생이름하나"), person("b1", "학생이름둘")]), None
    after1 = view([person("a1", "학생이름하나")], unassigned=[person("b1", "학생이름둘")])
    after2 = view([person("a1", "학생이름하나")], unassigned=[person("b1", "학생이름둘")])
    after2["teams"][1]["members"] = [person("b1", "학생이름둘")]
    after2["unassigned"] = []
    return {"1": record(before1, after1), "2": record(after1, after2)}


def test_the_warning_is_at_the_top_of_the_practice_tab(pool):
    at = practice_app()
    assert any(WARNING in str(w.value) and "모두 지웁니다" in str(w.value) for w in at.warning)


def test_a_fresh_session_has_no_timeline_and_says_there_is_no_record(pool):
    at = practice_app()
    assert step_buttons(at) == {} and not any(b.key == "practice_run_next" for b in at.button)
    assert any("저장한 기록이 없음" in str(e.value) for kind in ("markdown", "text", "info") for e in getattr(at, kind))


def test_the_timeline_shows_the_title_the_progress_and_each_step_in_order_with_a_one_line_summary(pool):
    names = {"a1": "학생이름하나", "b1": "학생이름둘"}
    at = practice_app(practice_units=units(), practice_records=two_done(), practice_names=names, practice_title="쉬움 시나리오")
    assert any(s.value == "쉬움 시나리오" for s in at.subheader)
    assert any("3단계 가운데 2단계까지 실행함" in str(c.value) for c in at.caption)
    buttons = step_buttons(at)
    assert list(buttons) == ["practice_step_1"]  # 2단계는 지금 보이는 단계이고 3-1, 3-2는 아직 실행하지 않음
    assert "학생이름하나가 팀1에 지원" in buttons["practice_step_1"].label
    html = timeline_html(at)
    assert html.index("학생이름둘이 팀2에 지원") < html.index("모집 마감") < html.index("AI 배정")
    for kind in ("sel", "next", "wait"):
        assert present(at, f"practice_row_{kind}_{'2' if kind == 'sel' else '3_1' if kind == 'next' else '3_2'}")


def test_the_timeline_has_no_fixed_height_box(pool):
    source = (ROOT / "mp" / "practice_view.py").read_text(encoding="utf-8")
    assert "height=640" not in source and "container(height" not in source


def test_executed_steps_are_pressable_cards_and_the_others_are_plain_text_with_a_status_word(pool):
    at = practice_app(practice_units=units(), practice_records=two_done())
    button = step_buttons(at)["practice_step_1"]
    assert not button.disabled and button.help == "이 단계 보기"
    html = timeline_html(at)
    assert "▶" in html and "다음 차례" in html and "실행 전" in html  # 보는 단계, 다음 차례, 아직 실행하지 않음
    assert "보는 중" not in screen_text(at) and "보는 중" not in html
    assert "모델 호출 없음" not in html and "실제 모델 호출함" not in html


def test_the_run_button_says_the_step_to_run_and_the_next_step_is_marked(pool):
    at = practice_app(practice_units=units(), practice_records=two_done())
    assert run_label(at) == "3-1단계 실행" and not at.button(key="practice_run_next").disabled


def test_the_last_executed_step_is_shown_first_and_pressing_a_step_shows_its_situation_without_running(pool, monkeypatch):
    calls = []
    stub_run_unit(monkeypatch, calls)
    at = practice_app(practice_units=units(), practice_records=two_done())
    assert any(s.value == "▶ 2단계의 상황" for s in at.subheader)
    at.button(key="practice_step_1").click().run()
    assert not at.exception and calls == []
    assert any(s.value == "▶ 1단계의 상황" for s in at.subheader)
    assert "학생이름하나" in board_html(at)
    assert any("지원함" in str(e.value) for e in at.markdown)
    assert present(at, "practice_row_sel_1") and not present(at, "practice_step_1") and present(at, "practice_step_2")


def test_previous_and_next_buttons_move_only_between_executed_steps(pool):
    at = practice_app(practice_units=units(), practice_records=two_done())
    assert at.button(key="practice_next").disabled and not at.button(key="practice_prev").disabled
    assert at.button(key="practice_prev").label == "‹ 이전 단계 보기" and at.button(key="practice_next").label == "다음 단계 보기 ›"
    at.button(key="practice_prev").click().run()
    assert any(s.value == "▶ 1단계의 상황" for s in at.subheader)
    assert at.button(key="practice_prev").disabled and not at.button(key="practice_next").disabled
    at.button(key="practice_next").click().run()
    assert any(s.value == "▶ 2단계의 상황" for s in at.subheader)


def test_the_situation_has_one_sentence_and_the_expected_actual_and_verdict_line(pool):
    at = practice_app(practice_units=units(), practice_records=two_done())
    line = texts(at, "practice_verdict").replace("**", "")
    assert "기대 결과 승인" in line and "실제 결과 승인" in line and "green[○ 일치]" in line
    assert "badge" not in line
    assert any("팀2에 지원함" in str(e.value) for e in at.markdown)


def test_the_board_marks_new_members_with_a_symbol_and_the_previous_state_side_by_side_is_off_until_asked(pool):
    at = practice_app(practice_units=units(), practice_records=two_done())
    html = board_html(at)
    assert "pb-new" in html and "+" in html and "빈 자리" in html
    for key in ("practice_before", "practice_after"):
        try:
            at.get_by_key(key)
            raise AssertionError(f"{key}가 처음부터 있음")
        except KeyError:
            pass
    at.toggle(key="practice_show_before").set_value(True).run()
    assert not at.exception
    assert "학생이름둘" in texts(at, "practice_after") and "학생이름둘" in texts(at, "practice_before")


def test_a_waiting_step_is_not_pressable_and_nothing_runs_until_the_run_button_is_pressed(pool, monkeypatch):
    calls = []
    stub_run_unit(monkeypatch, calls)
    at = practice_app(practice_units=units(), practice_records={})
    assert step_buttons(at) == {}  # 실행한 단계가 없으면 누를 수 있는 칸이 없음
    assert "다음 차례" in timeline_html(at) and "실행 전" in timeline_html(at)
    assert run_label(at) == "1단계 실행"
    assert calls == []


def test_pressing_the_run_button_runs_the_next_step_once_and_shows_it(pool, monkeypatch):
    calls = []
    stub_run_unit(monkeypatch, calls)
    at = practice_app(practice_units=units(), practice_records={})
    at.button(key="practice_run_next").click().run()
    assert not at.exception and len(calls) == 1
    assert "1" in at.session_state["practice_records"]
    at.run()
    assert len(calls) == 1
    assert any(s.value == "▶ 1단계의 상황" for s in at.subheader)
    assert run_label(at) == "2단계 실행"


def test_a_pending_request_runs_once_and_is_not_repeated_on_the_next_run(pool, monkeypatch):
    calls = []
    stub_run_unit(monkeypatch, calls)
    at = practice_app(practice_units=units(), practice_records={}, practice_pending="1")
    assert len(calls) == 1
    at.run()
    assert len(calls) == 1
    assert "1" in at.session_state["practice_records"]


def before_assign():
    return {**two_done(), "3-1": record(view(), view(), action="마감")}


def ai_part(calls=False, called=0, source="앱이 직접 배정"):
    return {"calls_models": calls, "called": called, "source": source, "pairs": [], "checks": [], "lines": []}


def capture_plans(monkeypatch, calls, plans):
    def fake(pool, admin_id, actions, ai_plan=None):
        calls.append([a.action for a in actions])
        plans.append(ai_plan)
        v = view([person("a1", "학생A")])
        return record(v, v, action=actions[0].action)
    monkeypatch.setattr(practice_run, "run_unit", fake)


def test_the_real_model_toggle_is_on_by_default_and_the_run_button_just_says_the_step(pool, monkeypatch):
    monkeypatch.setattr(service, "count_ai_calls_today", lambda pool_: 5)
    at = practice_app(practice_units=units(), practice_records=before_assign())
    assert at.toggle(key="practice_ai_on").value is True
    assert run_label(at) == "3-2단계 실행"
    assert any("오늘" in str(e.value) and "5" in str(e.value) for kind in ("markdown", "caption", "text") for e in getattr(at, kind))
    assert any("실제 모델을 부름" in str(e.value) for e in at.markdown)
    at.toggle(key="practice_ai_on").set_value(False).run()
    assert not at.exception
    assert any("모델을 부르지 않음" in str(e.value) for e in at.markdown)


def test_running_the_assign_step_with_the_toggle_on_calls_the_models_without_a_confirm_window(pool, monkeypatch):
    monkeypatch.setattr(service, "count_ai_calls_today", lambda pool_: 5)
    monkeypatch.setattr(practice_view, "get_secret", lambda name: "dummy-key")
    calls, plans = [], []
    capture_plans(monkeypatch, calls, plans)
    at = practice_app(practice_units=units(), practice_records=before_assign())
    at.button(key="practice_run_next").click().run()
    assert not at.exception and calls == [["배정"]]
    assert len(plans[0].models) == 3 and plans[0].ask_factory is not None
    assert not any("앱이 규칙에 맞는 배정을 직접 찾습니다" in str(e.value) for e in at.markdown)


def test_running_the_assign_step_with_the_toggle_off_opens_a_confirm_window_and_runs_nothing(pool, monkeypatch):
    monkeypatch.setattr(service, "count_ai_calls_today", lambda pool_: 5)
    calls, plans = [], []
    capture_plans(monkeypatch, calls, plans)
    at = practice_app(practice_units=units(), practice_records=before_assign())
    at.toggle(key="practice_ai_on").set_value(False).run()
    at.button(key="practice_run_next").click().run()
    assert not at.exception and calls == []
    assert "practice_pending" not in at.session_state
    text = " ".join(str(e.value) for e in at.markdown)
    assert "실제 AI 모델 호출이 꺼져 있습니다. 이대로 실행하면 AI를 부르지 않고 앱이 규칙에 맞는 배정을 직접 찾습니다." in text
    labels = {b.key: b.label for b in at.button}
    assert labels["practice_confirm_go"] == "앱이 직접 배정으로 실행" and labels["practice_confirm_cancel"] == "취소"
    at.run()  # 창을 닫은 뒤의 다음 실행: 창이 다시 뜨지 않고 아무것도 실행하지 않음
    assert calls == [] and "practice_confirm_go" not in {b.key for b in at.button}


def test_the_confirmed_run_without_models_gives_the_run_no_models_and_the_other_steps_never_ask(pool, monkeypatch):
    monkeypatch.setattr(service, "count_ai_calls_today", lambda pool_: 5)
    calls, plans = [], []
    capture_plans(monkeypatch, calls, plans)
    at = practice_app(practice_units=units(), practice_records=before_assign())
    at.toggle(key="practice_ai_on").set_value(False).run()
    at.session_state["practice_pending"] = "3-2"  # 확인 창에서 "앱이 직접 배정으로 실행"을 누른 뒤의 상태
    at.run()
    assert calls == [["배정"]] and plans[0].models == () and plans[0].ask_factory is None
    # 배정이 아닌 단계는 토글과 상관없이 확인 창 없이 바로 실행함
    at = practice_app(practice_units=units(), practice_records={})
    at.button(key="practice_run_next").click().run()
    assert "practice_confirm" not in at.session_state and len(calls) == 2


def test_an_exhausted_daily_quota_counts_as_toggle_off_and_asks_for_confirmation(pool, monkeypatch):
    monkeypatch.setattr(service, "count_ai_calls_today", lambda pool_: 49)
    calls, plans = [], []
    capture_plans(monkeypatch, calls, plans)
    at = practice_app(practice_units=units(), practice_records=before_assign())
    at.button(key="practice_run_next").click().run()
    assert calls == [] and any("직접 찾습니다" in str(e.value) for e in at.markdown)


def test_an_executed_assign_step_says_who_assigned_and_the_sentence_says_no_ai_was_called(pool):
    rec = record(view(), view(), action="배정")
    rec["ai"] = ai_part()
    at = practice_app(practice_units=units(), practice_records={**before_assign(), "3-2": rec})
    assert "AI 안 부름 · 앱이 직접 배정" in texts(at, "practice_checks")
    assert "AI 안 부름 · 앱이 직접 배정" in timeline_html(at)
    assert any("AI를 부르지 않음(실제 AI 모델 호출을 껐음). 앱이 규칙에 맞는 배정을 직접 찾음" in str(e.value) for e in at.markdown)


def test_the_finish_line_replaces_the_run_button_when_every_step_is_done(pool):
    records = {**before_assign(), "3-2": record(view(), view(), action="배정")}
    at = practice_app(practice_units=units(), practice_records=records)
    assert not present(at, "practice_run_next")
    line = texts(at, "practice_finish")
    assert "시나리오 끝" in line and "3단계를 모두 실행함" in line and "기대와 일치 4/4" in line
    assert "불일치" not in line and "규칙" not in line  # 단계표에 확정이 없으면 규칙 문구도 없음


def test_the_finish_line_counts_mismatches_in_red(pool):
    records = {**before_assign(), "3-2": record(view(), view(), action="배정", status="거절")}
    at = practice_app(practice_units=units(), practice_records=records)
    line = texts(at, "practice_finish")
    assert "기대와 일치 3/4" in line and ":red[**불일치 1**]" in line


def test_the_finish_window_opens_once_right_after_the_last_step_runs(pool, monkeypatch):
    calls = []
    stub_run_unit(monkeypatch, calls)
    at = practice_app(practice_units=units(), practice_records=before_assign(), practice_pending="3-2")
    assert not at.exception and len(calls) == 1
    text = " ".join(str(e.value) for e in at.markdown)
    assert "실행한 단계: **3단계**" in text and "기대와 일치한 하위 단계: **4/4**" in text
    assert "practice_finish_close" in {b.key for b in at.button}
    at.run()  # 닫은 뒤에는 다시 뜨지 않음
    assert "practice_finish_close" not in {b.key for b in at.button}
    assert present(at, "practice_finish")


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
