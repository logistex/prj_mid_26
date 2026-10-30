# 2026-10-30 22:50 KST
"""AI 호출 모듈 시험(PRD_step3 10.2절). 가짜 OpenRouter 서버만 쓰고 실제 호출은 하지 않음. DB를 쓰지 않음

느린 시험(진짜 120초 상수 확인)은 RUN_SLOW=1일 때만 실행함
"""
import json
import os
import time

import pytest

from fake_openrouter import FakeOpenRouter
from mp import ai
from mp.config import ai_config, validate_models, MODELS

PL, WP, TT = "기획자", "웹 프로그래머", "테스터"
KEY = "sk-or-v1-fake-test-key-0000000000"


def st(no, main, *subs):
    return {"id": int(no), "student_no": str(no), "name": f"학생{no}", "main_role": main, "sub_roles": list(subs)}


TEAMS = [
    {"team_no": 1, "name": "팀1", "members": [st(1, PL)]},
    {"team_no": 2, "name": "팀2", "members": [st(2, WP)]},
]
UNASSIGNED = [st(3, WP), st(4, PL)]
GOOD = json.dumps({"assignments": [{"student_no": "3", "team_no": 1}, {"student_no": "4", "team_no": 2}]})


def never_fail(pairs):
    return None


@pytest.fixture
def server():
    s = FakeOpenRouter({}).start()
    yield s
    s.stop()


def ask(server, model, timeout=5, check=never_fail, tick=None):
    return ai.ask_model(KEY, model, ai.build_messages(TEAMS, UNASSIGNED), timeout, server.url, check, tick)


def test_success_and_key_header_is_sent(server):
    server.behaviors["m:free"] = ("content", GOOD)
    a = ask(server, "m:free")
    assert a.outcome == ai.SUCCESS and a.pairs == [("3", 1), ("4", 2)]
    assert server.requests == [("m:free", True)]


def test_code_block_and_text_around_json_are_read(server):
    server.behaviors["m:free"] = ("content", "배정안입니다.\n```json\n" + GOOD + "\n```\n끝")
    assert ask(server, "m:free").outcome == ai.SUCCESS


@pytest.mark.parametrize(
    "behavior,outcome",
    [
        (("empty",), ai.EMPTY),
        (("content", "   "), ai.EMPTY),
        (("status", 429), ai.HTTP_ERROR),
        (("status", 500), ai.HTTP_ERROR),
        (("error200", 429), ai.HTTP_ERROR),
        (("content", "배정할 수 없습니다"), ai.BAD_FORMAT),
        (("content", '{"assignments": "없음"}'), ai.BAD_FORMAT),
        (("content", '{"assignments": [{"student_no": "3"}]}'), ai.BAD_FORMAT),
    ],
)
def test_failures_are_classified(server, behavior, outcome):
    server.behaviors["m:free"] = behavior
    a = ask(server, "m:free")
    assert a.outcome == outcome
    assert KEY not in a.detail and "sk-or" not in a.detail


def test_http_error_detail_has_the_status_code(server):
    server.behaviors["m:free"] = ("status", 429)
    assert "429" in ask(server, "m:free").detail


def test_empty_response_detail_has_finish_reason(server):
    server.behaviors["m:free"] = ("empty",)
    assert "length" in ask(server, "m:free").detail


def test_check_failure_keeps_the_reason(server):
    server.behaviors["m:free"] = ("content", GOOD)
    a = ask(server, "m:free", check=lambda pairs: "검사 4번: 팀1에 주 역할이 같은 학생이 있음")
    assert a.outcome == ai.CHECK_FAILED and "검사 4번" in a.detail


def test_connection_error_is_classified():
    a = ai.ask_model(KEY, "m:free", [], 3, "http://127.0.0.1:9", never_fail)
    assert a.outcome == ai.CONNECTION_ERROR
    assert KEY not in a.detail


def test_total_wait_limit_cuts_a_slow_response_and_reports_ticks(server):
    server.behaviors["slow:free"] = ("sleep", 30, GOOD)
    ticks = []
    t0 = time.monotonic()
    a = ask(server, "slow:free", timeout=2, tick=ticks.append)
    elapsed = time.monotonic() - t0
    assert a.outcome == ai.TIMEOUT
    assert 1.9 <= elapsed < 4.0
    assert len(ticks) >= 2  # 기다리는 동안 경과 시간을 알림


def test_a_response_that_arrives_just_before_the_limit_is_accepted(server):
    server.behaviors["m:free"] = ("sleep", 1, GOOD)
    assert ask(server, "m:free", timeout=5).outcome == ai.SUCCESS


# ---- 1차에서 3차로 넘어가기 ----

def run_propose(server, behaviors, limit=2):
    server.behaviors.update(behaviors)
    models = list(behaviors)
    progress = ai.Progress()
    logs = []

    def do_ask(n, model, tick):
        return ai.ask_model(KEY, model, ai.build_messages(TEAMS, UNASSIGNED), limit, server.url, never_fail, tick)

    pairs, source, attempts = ai.propose(models, do_ask, [("3", 2), ("4", 1)], lambda n, a: logs.append((n, a.outcome)), progress, limit)
    return pairs, source, attempts, logs, progress


def test_first_model_success_does_not_call_the_others(server):
    pairs, source, attempts, logs, progress = run_propose(
        server, {"a:free": ("content", GOOD), "b:free": ("content", GOOD), "c:free": ("content", GOOD)}
    )
    assert source.startswith("1차 모델") and pairs == [("3", 1), ("4", 2)]
    assert server.count("b:free") == 0 and server.count("c:free") == 0
    assert logs == [(1, ai.SUCCESS)]


def test_first_model_timeout_moves_on_to_the_second(server):
    t0 = time.monotonic()
    pairs, source, attempts, logs, progress = run_propose(
        server, {"a:free": ("sleep", 30, GOOD), "b:free": ("content", GOOD), "c:free": ("content", GOOD)}, limit=2
    )
    assert source.startswith("2차 모델")
    assert [o for _, o in logs] == [ai.TIMEOUT, ai.SUCCESS]
    assert time.monotonic() - t0 < 6
    assert "1차 모델: 시간 초과" in progress.text() and "2차 모델로 넘어감" in progress.text()
    assert server.count("a:free") == 1  # 같은 모델을 다시 부르지 않음


def test_rate_limit_then_empty_then_success(server):
    pairs, source, attempts, logs, progress = run_propose(
        server, {"a:free": ("status", 429), "b:free": ("empty",), "c:free": ("content", GOOD)}
    )
    assert source.startswith("3차 모델")
    assert [o for _, o in logs] == [ai.HTTP_ERROR, ai.EMPTY, ai.SUCCESS]


def test_all_three_fail_so_the_app_assigns_by_itself(server):
    pairs, source, attempts, logs, progress = run_propose(
        server, {"a:free": ("sleep", 30, GOOD), "b:free": ("status", 500), "c:free": ("content", "설명만 있음")}
    )
    assert source == ai.APP_FALLBACK and pairs == [("3", 2), ("4", 1)]
    assert [o for _, o in logs] == [ai.TIMEOUT, ai.HTTP_ERROR, ai.BAD_FORMAT]
    assert "3차까지 실패해 앱이 직접 배정함" in progress.text()


def test_waiting_line_names_the_model_and_the_seconds(server):
    seen = []
    server.behaviors["a:free"] = ("sleep", 30, GOOD)
    server.behaviors["b:free"] = ("content", GOOD)
    progress = ai.Progress(on_change=lambda p: seen.append(p.waiting))

    def do_ask(n, model, tick):
        return ai.ask_model(KEY, model, [], 2.5, server.url, never_fail, tick)

    ai.propose(["a:free", "b:free"], do_ask, [], lambda n, a: None, progress, 2.5)
    waits = [w for w in seen if w]
    assert any(w.startswith("1차 모델(a:free) 응답을 기다리는 중: 0초 / 2.5초") for w in waits)
    assert any("1초 / 2.5초" in w for w in waits)


# ---- 모델 이름 검사 ----

def test_default_models_are_three_free_models_and_not_the_auto_router():
    assert len(MODELS) == 3 and len(set(MODELS)) == 3
    assert validate_models(MODELS) == MODELS
    with pytest.raises(ValueError):
        validate_models(["openrouter/free"])
    with pytest.raises(ValueError):
        validate_models(["nvidia/nemotron-3-ultra-550b-a55b"])


def test_ai_config_defaults_and_env_override(monkeypatch):
    for k in ("MP_AI_MODELS", "MP_AI_TIMEOUT", "MP_AI_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    models, timeout, base = ai_config()
    assert models == MODELS and timeout == 120 and base == "https://openrouter.ai/api/v1"
    monkeypatch.setenv("MP_AI_MODELS", "x/y:free, z/w:free")
    monkeypatch.setenv("MP_AI_TIMEOUT", "7")
    assert ai_config()[:2] == (("x/y:free", "z/w:free"), 7.0)


@pytest.mark.skipif(os.environ.get("RUN_SLOW") != "1", reason="약 2분 걸리므로 RUN_SLOW=1일 때만 실행")
def test_real_120_second_limit_cuts_the_first_model_and_moves_on(server, monkeypatch):
    monkeypatch.delenv("MP_AI_TIMEOUT", raising=False)
    models, limit, _ = ai_config()
    assert limit == 120
    server.behaviors["a:free"] = ("sleep", 140, GOOD)
    server.behaviors["b:free"] = ("content", GOOD)

    def do_ask(n, model, tick):
        return ai.ask_model(KEY, model, [], limit, server.url, never_fail, tick)

    t0 = time.monotonic()
    pairs, source, attempts = ai.propose(["a:free", "b:free"], do_ask, [], lambda n, a: None, ai.Progress(), limit)
    elapsed = time.monotonic() - t0
    assert attempts[0].outcome == ai.TIMEOUT
    assert 119 <= attempts[0].seconds < 123
    assert source.startswith("2차 모델")
    print(f"\n1차 모델이 끊긴 시각: {attempts[0].seconds:.1f}초, 전체 {elapsed:.1f}초")


# ---- 원인 분석용 기록: finish_reason, 토큰 수, 응답 앞부분 ----

def test_empty_response_records_finish_reason_tokens_and_reasoning_head(server):
    server.behaviors["m:free"] = ("empty",)
    a = ask(server, "m:free")
    assert a.outcome == ai.EMPTY
    assert a.finish_reason == "length"
    assert (a.prompt_tokens, a.completion_tokens, a.reasoning_tokens) == (900, 4000, 4000)
    assert a.head.startswith("[추론] 먼저 규칙을 정리해 보면")
    assert len(a.head) <= ai.HEAD_LIMIT


def test_success_records_tokens_and_content_head(server):
    server.behaviors["m:free"] = ("content", GOOD)
    a = ask(server, "m:free")
    assert a.finish_reason == "stop"
    assert (a.prompt_tokens, a.completion_tokens, a.reasoning_tokens) == (900, 120, 20)
    assert a.head.startswith('{"assignments"')


def test_long_content_head_is_cut_to_500_characters(server):
    server.behaviors["m:free"] = ("content", "가" * 3000)
    a = ask(server, "m:free")
    assert a.outcome == ai.BAD_FORMAT and len(a.head) == ai.HEAD_LIMIT


def test_http_error_has_no_token_fields(server):
    server.behaviors["m:free"] = ("status", 429)
    a = ask(server, "m:free")
    assert a.finish_reason == "" and a.prompt_tokens is None and a.head == ""


def test_max_tokens_is_sent_to_the_server(server):
    server.behaviors["m:free"] = ("content", GOOD)
    ai.ask_model(KEY, "m:free", [], 5, server.url, never_fail)
    ai.ask_model(KEY, "m:free", [], 5, server.url, never_fail, None, 12000)
    assert [b["max_tokens"] for b in server.bodies] == [ai.MAX_TOKENS, 12000]
    assert server.bodies[0]["reasoning"] == {"effort": "low"}


# ---- 프롬프트와 설정(PRD_step3 15장 대응) ----

def test_prompt_says_not_to_assign_students_who_already_have_a_team():
    text = ai.build_messages(TEAMS, UNASSIGNED)[1]["content"]
    assert "이미 있는 학생은 옮기지 않으며" in text and "assignments에 넣지 않습니다" in text
    assert "assignments의 항목 수는 students_without_team의 학생 수와 같아야 합니다" in text
    assert "JSON만 쓰십시오" in text and "코드 블록 표시" in text
    # 데이터에는 기존 팀원과 팀이 없는 학생이 이름과 역할을 포함해 구분되어 들어감
    data = json.loads(text.split("데이터:\n", 1)[1])
    assert [m["student_no"] for m in data["teams"][0]["members"]] == ["1"]
    assert [s["student_no"] for s in data["students_without_team"]] == ["3", "4"]
    assert set(data["students_without_team"][0]) == {"student_no", "name", "main_role", "sub_roles"}


def test_default_max_tokens_is_12000_and_models_are_the_chosen_three():
    assert ai.MAX_TOKENS == 12000
    assert MODELS == (
        "cohere/north-mini-code:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "poolside/laguna-s-2.1:free",
    )
