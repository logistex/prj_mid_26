# 2026-10-30 22:50 KST
"""시험과 화면 재현에 쓰는 가짜 OpenRouter 서버. 실제 호출 없이 지연, 429, 빈 응답 같은 실패를 만듦

모델 이름마다 동작을 정함: ("content", 글), ("sleep", 초, 글), ("status", 코드), ("empty",), ("error200", 코드)
화면 재현용으로 직접 실행하면 모델 이름별 기본 동작으로 뜸: python tests/fake_openrouter.py 8899 [올바른 배정안.json]
"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeOpenRouter:
    def __init__(self, behaviors, port=0):
        self.behaviors = behaviors
        self.requests = []  # (모델 이름, Authorization 머리글이 있었는지)
        self.bodies = []  # 받은 요청 본문(max_tokens 같은 값을 확인하는 시험용)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                model = body.get("model", "")
                outer.requests.append((model, self.headers.get("Authorization", "").startswith("Bearer ")))
                outer.bodies.append(body)
                spec = outer.behaviors.get(model, ("status", 404))
                kind = spec[0]
                if kind == "sleep":
                    time.sleep(spec[1])
                    kind, spec = "content", ("content", spec[2])
                if kind == "status":
                    return self._send(spec[1], {"error": {"message": "Provider returned error", "code": spec[1]}})
                if kind == "error200":
                    return self._send(200, {"error": {"message": "Provider returned error", "code": spec[1]}})
                if kind == "empty":  # 추론에 토큰을 모두 써서 content가 빈 응답
                    return self._send(200, {
                        "choices": [{"message": {"content": "", "reasoning": "먼저 규칙을 정리해 보면 " * 40}, "finish_reason": "length"}],
                        "usage": {"prompt_tokens": 900, "completion_tokens": 4000, "completion_tokens_details": {"reasoning_tokens": 4000}},
                    })
                return self._send(200, {
                    "choices": [{"message": {"content": spec[1]}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 900, "completion_tokens": 120, "completion_tokens_details": {"reasoning_tokens": 20}},
                })

            def _send(self, status, payload):
                data = json.dumps(payload).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # 클라이언트가 한도를 넘겨 먼저 끊음

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def count(self, model):
        return sum(1 for m, _ in self.requests if m == model)


DEMO_BEHAVIORS = {
    "fake/slow-model:free": ("sleep", 600, "{}"),  # 한도를 넘겨도 응답하지 않는 모델
    "fake/rate-limited-model:free": ("status", 429),
    "fake/empty-model:free": ("empty",),
    "fake/garbage-model:free": ("content", "배정안을 만들 수 없습니다"),
}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    behaviors = dict(DEMO_BEHAVIORS)
    if len(sys.argv) > 2:  # 올바른 배정안 JSON 파일을 주면 fake/ok-model:free가 그 글로 답함
        with open(sys.argv[2], encoding="utf-8") as f:
            behaviors["fake/ok-model:free"] = ("content", f.read())
    server = FakeOpenRouter(behaviors, port).start()
    print("가짜 OpenRouter 서버:", server.url, flush=True)
    threading.Event().wait()
