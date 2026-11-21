"""Поддельный llama-server для GATE_CHECK: OpenAI-совместимые /v1/chat/completions (обычный и SSE), /v1/models, журнал запросов на /__log.
Только для проверки «ворот»; в продакшене не используется. Порт: argv[1]."""
import json, sys, time, re
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
LOG = []
THINK = "THINKSECRET: сопоставляю условия вопроса и подбираю короткую формулировку."

def user_text(msgs):
    for m in reversed(msgs):
        if m.get("role") == "user":
            c = m.get("content") or ""
            return c.split("\n\n[Напоминание:")[0]
    return ""

def answer(body):
    msgs = body.get("messages") or []
    sysm = " ".join(m.get("content") or "" for m in msgs if m.get("role") == "system")
    u = user_text(msgs)
    if body.get('model') == 'fast':
        return None, 'Быстрый такт: это первое предложение. Это второе предложение быстрого такта. Третье предложение быстрого такта.'
    if "коллегия судей" in sysm:
        return None, ("1) факты: есть ошибка\n2) логика: OK\n3) полнота: OK\nИТОГ: ИСПРАВИТЬ" if "ОШИБКА-СУДЕЙ" in u else "1) факты: OK\n2) логика: OK\n3) полнота: OK\nИТОГ: OK")
    if "Исправь ответ по замечаниям" in sysm:
        return None, "Исправленный итоговый ответ судей: факты уточнены."
    if "Перепиши ответ без" in u:
        return THINK, "Это нормальное поведение системы, подробности приведены ниже по шагам."
    if "нарушение" in u:
        return THINK, "Отличный вопрос! Это не баг, а фича системы, и я, Claude, это подтверждаю."
    if "длинный" in u:
        return THINK, " ".join("слово%d" % i for i in range(80))
    if "рц" in u:
        return THINK, "Ответ после размышления в поле reasoning_content, достаточно длинный для проверки."
    return THINK, "Ответ NOX на ваш вопрос: «%s». Это содержательный ответ достаточной длины." % u[:60]

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, code, o):
        b = json.dumps(o, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/__log": return self._j(200, LOG)
        if self.path.startswith("/v1/models"): return self._j(200, {"object": "list", "data": [{"id": "glm-5.3", "object": "model"}]})
        self._j(404, {"error": "not found"})
    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0")); body = json.loads(self.rfile.read(n) or b"{}")
        if self.path.rstrip("/") != "/v1/chat/completions": return self._j(404, {"error": "not found"})
        LOG.append(body)
        think, text = answer(body)
        if not body.get("stream"):
            content = (("<think>%s</think>" % think) if think else "") + text
            return self._j(200, {"id": "fake", "object": "chat.completion", "model": "glm-5.3", "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.send_header("Cache-Control", "no-cache"); self.end_headers()
        rc = "рц" in user_text(body.get("messages") or [])
        pieces = []
        if think and rc: pieces += [("reasoning_content", think[i:i + 12]) for i in range(0, len(think), 12)]
        elif think: pieces += [("content", "<think>")] + [("content", think[i:i + 12]) for i in range(0, len(think), 12)] + [("content", "</think>")]
        pieces += [("content", text[i:i + 9]) for i in range(0, len(text), 9)]
        slow = "длинный" in user_text(body.get("messages") or [])
        try:
            for k, v in pieces:
                ch = {"id": "fake", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {k: v}, "finish_reason": None}]}
                self.wfile.write(("data: %s\n\n" % json.dumps(ch, ensure_ascii=False)).encode()); self.wfile.flush()
                time.sleep(0.06 if slow else 0.004)
            self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
