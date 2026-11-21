"""Помощники для тестов агента: поддельный шлюз NOX (loopback), временный git-репозиторий, конфиг. Сети нет."""
import json, os, subprocess, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .config import Config


def mkcfg(tmp, **env):
    e = {"NOX_AGENT_STATE": os.path.join(tmp, "state"), "NOX_AGENT_ALLOW_ROOT": "1", "NOX_AGENT_REPO": os.path.join(tmp, "repo"), "NOX_AGENT_WORK": os.path.join(tmp, "work"),
         "NOX_AGENT_ALLOW_PRIVATE_FETCH": "1", "NOX_AGENT_HEALTH_INTERVAL": "0", "NOX_AGENT_INBOX": os.path.join(tmp, "inbox.jsonl"), "NOX_AGENT_QUEUE": os.path.join(tmp, "queue.jsonl"),
         "NOX_AGENT_PLAN": "0", "NOX_AGENT_TEST_TIMEOUT": "120"}
    e.update({k: str(v) for k, v in env.items()})
    return Config(env=e)


def tool_resp(calls, content="", tokens=50):
    """Ответ шлюза с нативными tool_calls. calls: [(name, args_dict)]"""
    tcs = [{"id": "call_%d" % i, "type": "function", "function": {"name": n, "arguments": json.dumps(a, ensure_ascii=False)}} for i, (n, a) in enumerate(calls)]
    return {"choices": [{"index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": content, "tool_calls": tcs}}],
            "usage": {"prompt_tokens": tokens, "completion_tokens": 10, "total_tokens": tokens + 10}}


def text_resp(text, tokens=50):
    return {"choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": tokens, "completion_tokens": 10, "total_tokens": tokens + 10}}


class FakeGateway:
    """Сценарий: список ответов (dict) по порядку; {"hang": True} держит запрос до /v1/stop; callable(body)->dict. Запросы пишутся в .requests."""

    def __init__(self, script=None, default=None):
        self.script, self.default, self.requests, self.stops, self.active = list(script or []), default, [], [], []
        self.release = threading.Event()
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def _j(self, code, obj):
                b = json.dumps(obj).encode()
                try:
                    self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
                except OSError:
                    pass

            def do_GET(self):
                if self.path.startswith("/v1/nox/stats"): return self._j(200, {"active": list(outer.active)})
                self._j(404, {})

            def do_POST(self):
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(n) or b"{}")
                if self.path == "/v1/stop":
                    outer.stops.append(body.get("request_id"))
                    ok = body.get("request_id") in outer.active
                    outer.release.set()
                    return self._j(200, {"stopped": ok})
                outer.requests.append(body)
                item = outer.script.pop(0) if outer.script else outer.default
                if callable(item): item = item(body)
                if item is None: return self._j(500, {"error": "script exhausted"})
                if isinstance(item, dict) and item.get("hang"):
                    rid = "rid%d" % len(outer.requests)
                    outer.active.append(rid)
                    outer.release.wait(10)
                    outer.active.remove(rid)
                    return self._j(499, {"error": "stopped"})
                self._j(200, item)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.release.set()
        self.srv.shutdown(); self.srv.server_close()


GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def sh(cwd, *args):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=dict(os.environ, **GIT_ENV))
    if r.returncode: raise RuntimeError("%s: %s" % (args, r.stderr))
    return r.stdout.strip()


def make_repo(path, red=False):
    """git-репозиторий с nox-control/agent/test_ok.py; red=True: тест падает."""
    os.makedirs(path, exist_ok=True)
    sh(path, "git", "init", "-q", "-b", "main")
    sh(path, "git", "config", "user.email", "t@t"); sh(path, "git", "config", "user.name", "t")
    touch(os.path.join(path, "nox-control", "agent", "__init__.py"), "")
    touch(os.path.join(path, "nox-control", "agent", "test_ok.py"),
          "import unittest\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(1, %d)\n" % (2 if red else 1))
    touch(os.path.join(path, "README.md"), "# demo\n")
    sh(path, "git", "add", "-A"); sh(path, "git", "commit", "-q", "-m", "init")
    return path


def touch(path, text="1"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: f.write(text)
