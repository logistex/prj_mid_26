# 2026-10-30 22:45 KST
"""OpenRouter 호출, 응답 읽기, 실패 분류, 모델마다 120초 제한, 1차에서 3차로 넘어가기(PRD_step3 5장)

키는 Authorization 헤더로만 보내고 요청과 헤더를 기록하거나 오류 문구에 넣지 않음
"""
import json
import re
import threading
import time
from dataclasses import dataclass, field

import requests

SUCCESS = "성공"
CHECK_FAILED = "검사 실패"
EMPTY = "빈 응답"
BAD_FORMAT = "형식 오류"
TIMEOUT = "시간 초과"
HTTP_ERROR = "HTTP 오류"
CONNECTION_ERROR = "연결 오류"

MAX_TOKENS = 12000  # 추론 토큰도 max_tokens에 들어가므로 넉넉하게 줌(4000에서는 추론에 다 써서 빈 응답이 났음, PRD_step3 15장)
APP_FALLBACK = "앱이 직접 배정"


HEAD_LIMIT = 500  # 기록에 남기는 응답 앞부분의 글자 수


@dataclass
class Attempt:
    model: str
    outcome: str
    seconds: float
    detail: str = ""
    pairs: list = field(default_factory=list)
    # 원인 분석용 기록(PRD_step3 8장): 응답이 왔을 때만 채워짐
    finish_reason: str = ""
    prompt_tokens: int = None
    completion_tokens: int = None
    reasoning_tokens: int = None
    head: str = ""


def _student_line(s):
    return {
        "student_no": s["student_no"],
        "name": s["name"],
        "main_role": s["main_role"],
        "sub_roles": s["sub_roles"],
    }


def build_messages(teams, unassigned):
    """지금의 팀 구성과 팀이 없는 학생을 설명하는 메시지(공고 2.5절 3항). 이미 팀에 있는 학생은 옮기지 않음"""
    data = {
        "teams": [
            {"team_no": t["team_no"], "name": t["name"], "members": [_student_line(m) for m in t["members"]]}
            for t in teams
        ],
        "students_without_team": [_student_line(s) for s in unassigned],
    }
    rules = (
        "students_without_team에 있는 학생(팀이 없는 학생)만 팀에 배정하십시오. "
        "teams의 members에 이미 있는 학생은 옮기지 않으며, 답의 assignments에 넣지 않습니다.\n"
        "규칙:\n"
        "1. students_without_team의 학생 모두를 빠짐없이, 한 학생당 한 팀에만 배정합니다. "
        "assignments의 항목 수는 students_without_team의 학생 수와 같아야 합니다.\n"
        "2. 배정한 뒤 모든 팀은 2명 이상 4명 이하여야 합니다(빈 팀도 2명 이상이 되어야 합니다).\n"
        "3. 한 팀 안에서 main_role(주 역할)이 같은 학생이 2명 이상이면 안 됩니다.\n"
        "4. 모든 팀에서 기획자와 웹 프로그래머를 서로 다른 학생이 1명씩 맡을 수 있어야 합니다. "
        "학생은 main_role 또는 sub_roles에 그 역할이 있으면 맡을 수 있습니다.\n"
        "답은 JSON만 쓰십시오. 설명, 풀이 과정, 코드 블록 표시(```)를 쓰지 않습니다. 형식: "
        '{"assignments": [{"student_no": "학번", "team_no": 팀 번호}, ...]}\n\n'
        "데이터:\n" + json.dumps(data, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": "당신은 팀 편성 도우미입니다. JSON만 답합니다."},
        {"role": "user", "content": rules},
    ]


def parse_response(text):
    """응답 글에서 [(학번, 팀 번호)]를 읽음. 코드 블록이나 앞뒤 설명이 붙어도 첫 {부터 마지막 }까지를 읽음"""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("JSON을 찾을 수 없음")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        raise ValueError("JSON을 읽을 수 없음")
    items = data.get("assignments") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("assignments 목록이 없음")
    pairs = []
    for item in items:
        try:
            pairs.append((str(item["student_no"]).strip(), int(item["team_no"])))
        except (KeyError, TypeError, ValueError):
            raise ValueError("항목에 student_no 또는 team_no가 없음")
    return pairs


def _clean(text, limit=80):
    """오류 문구에 키가 섞이지 않게 정리함"""
    text = re.sub(r"sk-[A-Za-z0-9_\-]+", "[키]", str(text))
    return " ".join(text.split())[:limit]


def _post(api_key, model, messages, timeout, base_url, out, max_tokens=MAX_TOKENS):
    """작업 스레드에서 호출함. 결과를 out에 담음(dict). 예외는 분류해서 담음"""
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "reasoning": {"effort": "low"},
    }
    try:
        resp = requests.post(
            base_url.rstrip("/") + "/chat/completions",
            json=body,
            headers={"Authorization": "Bearer " + api_key},
            timeout=(10, timeout + 5),
        )
        if resp.status_code >= 400:
            try:
                message = resp.json().get("error", {}).get("message", "")
            except ValueError:
                message = ""
            out["result"] = (HTTP_ERROR, _clean(f"HTTP {resp.status_code} {message}"), None)
            return
        data = resp.json()
        if "error" in data:
            err = data["error"] if isinstance(data["error"], dict) else {}
            out["result"] = (HTTP_ERROR, _clean(f"HTTP {err.get('code', '?')} {err.get('message', '')}"), None)
            return
        choice = data["choices"][0]
        message = choice.get("message", {})
        content = (message.get("content") or "").strip()
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        reasoning = (message.get("reasoning") or message.get("reasoning_content") or "").strip()
        out["meta"] = {
            "finish_reason": str(choice.get("finish_reason")),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": details.get("reasoning_tokens"),
            # content가 비었으면 추론 글의 앞부분을 남겨 무엇을 하다 끊겼는지 볼 수 있게 함
            "head": _clean(content, HEAD_LIMIT) if content else (("[추론] " + _clean(reasoning, HEAD_LIMIT - 5)) if reasoning else ""),
        }
        out["result"] = ("content", str(choice.get("finish_reason")), content)
    except requests.exceptions.RequestException as e:
        out["result"] = (CONNECTION_ERROR, type(e).__name__, None)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        out["result"] = (BAD_FORMAT, type(e).__name__, None)


def ask_model(api_key, model, messages, timeout, base_url, check, tick=None, max_tokens=MAX_TOKENS):
    """모델 1개를 불러 Attempt를 돌려줌. 호출한 때부터 응답을 받을 때까지의 전체 대기 시간이 timeout초를 넘으면 끊음

    check(pairs)는 배정안 검사로, 통과하면 None, 어기면 이유 문구를 돌려줌. tick(경과 초)는 기다리는 동안 1초마다 부름
    """
    start = time.monotonic()
    out = {}
    worker = threading.Thread(
        target=_post, args=(api_key, model, messages, timeout, base_url, out, max_tokens), daemon=True
    )
    worker.start()
    while worker.is_alive():
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            # 응답이 천천히 오다가 한도를 넘어도 끊음. 작업 스레드는 요청의 읽기 제한에 걸려 스스로 끝나고 늦은 결과는 버림
            return Attempt(model, TIMEOUT, elapsed, f"{timeout:g}초 넘음")
        if tick:
            tick(elapsed)
        worker.join(timeout=min(1.0, max(timeout - elapsed, 0.01)))
    seconds = time.monotonic() - start
    kind, detail, content = out.get("result", (CONNECTION_ERROR, "결과 없음", None))
    if kind != "content":
        return Attempt(model, kind, seconds, detail)
    meta = out.get("meta", {})
    if not content:
        return Attempt(model, EMPTY, seconds, f"finish_reason={detail}", **meta)
    try:
        pairs = parse_response(content)
    except ValueError as e:
        return Attempt(model, BAD_FORMAT, seconds, str(e), **meta)
    problem = check(pairs)
    if problem:
        return Attempt(model, CHECK_FAILED, seconds, problem, pairs, **meta)
    return Attempt(model, SUCCESS, seconds, "", pairs, **meta)


class Progress:
    """배정이 진행되는 동안 화면에 보여 줄 안내. note는 남는 줄, wait는 지금 기다리는 줄(계속 바뀜)"""

    def __init__(self, on_change=None):
        self.lines = []
        self.waiting = ""
        self._on_change = on_change

    def note(self, text):
        self.lines.append(text)
        self.waiting = ""
        self._changed()

    def wait(self, text):
        self.waiting = text
        self._changed()

    def text(self):
        return "\n".join([*self.lines, *([self.waiting] if self.waiting else [])])

    def _changed(self):
        if self._on_change:
            self._on_change(self)


def propose(models, ask, fallback_pairs, log, progress, limit):
    """모델을 1차, 2차, 3차 순으로 불러 검사를 통과한 첫 배정안을 씀. 모두 실패하면 앱이 직접 찾은 fallback_pairs를 씀

    ask(번호, 모델, tick)는 Attempt를 돌려줌. log(번호, Attempt)는 기록. 같은 모델을 다시 부르지 않음(공고 4.3절)
    돌려주는 값: (pairs, 출처 문구, Attempt 목록)
    """
    attempts = []
    for n, model in enumerate(models, start=1):
        attempt = ask(
            n,
            model,
            lambda elapsed, n=n, model=model: progress.wait(
                f"{n}차 모델({model}) 응답을 기다리는 중: {int(elapsed)}초 / {limit:g}초"
            ),
        )
        log(n, attempt)
        attempts.append(attempt)
        if attempt.outcome == SUCCESS:
            progress.note(f"{n}차 모델의 배정안이 검사를 통과함(소요 {attempt.seconds:.0f}초)")
            return attempt.pairs, f"{n}차 모델({model})", attempts
        reason = attempt.outcome + (f"({attempt.detail})" if attempt.detail else "")
        if n < len(models):
            progress.note(f"{n}차 모델: {reason} → {n + 1}차 모델로 넘어감")
        else:
            progress.note(f"{n}차 모델: {reason} → 3차까지 실패해 앱이 직접 배정함")
    return fallback_pairs, APP_FALLBACK, attempts
