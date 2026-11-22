"""pv01_e2e (ACT-06): сквозная приёмка PV-01 по HTTP шлюза NOX (stdlib).

Цепочка: S1 быстрый маршрут -> S2 мини-чат (тот же nox_session, без истории в теле) -> S3 источник факта (поиск в
памяти + провенанс в ответе) -> S4 правка (сервер обязан вернуть ok:true, чтение подтверждает) -> S5 «обновление страницы»
(новая сессия, чтение из S03) -> S6 ответ с правкой в НОВОМ диалоге -> S7 длинный ответ + STOP с серверной квитанцией.
Тестовый факт содержит nonce и в конце удаляется (обратимо). Код возврата 0 только если все шаги ok.

Параметры: флагами или одной ссылкой --url "https://host/glm/?memory=/memory/api&stop=/v1/stop&stats=/v1/nox/stats&chat=/v1/chat/completions&timeout=90".
Значения путей, начинающиеся с «/», — от корня хоста; по умолчанию chat/stop/stats = <путь ссылки>/v1/...; memory = /memory/api.
Квитанция: --receipt /root/nox/receipts/ACT-PV01.json. Запускать с S1 или ПК; ничего не пишет кроме тестового факта (потом удаляется).
"""
import argparse
import http.client
import json
import os
import secrets
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit

LONG_Q = "Напиши очень подробный разбор из 40 пунктов о том, как устроен гомеостаз у живых организмов. Каждый пункт — абзац."


class Cfg:
    def __init__(self, url=None, base=None, memory=None, chat=None, stop=None, stats=None, timeout=60.0, fast_timeout=20.0,
                 first_frame_timeout=25.0, expect_tier="fast", mini_mode="session", headers=None):
        q = {}
        if url:
            u = urlsplit(url)
            base = "%s://%s" % (u.scheme, u.netloc)
            prefix = u.path.rstrip("/")
            if prefix.endswith((".html", ".htm")):
                prefix = prefix.rsplit("/", 1)[0]
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
        else:
            prefix = ""
        if not base:
            raise ValueError("need --url or --base")
        self.origin = base.rstrip("/")
        pick = lambda key, arg, default: q.get(key) or arg or default
        self.chat = pick("chat", chat, prefix + "/v1/chat/completions")
        self.stop = pick("stop", stop, prefix + "/v1/stop")
        self.stats = pick("stats", stats, prefix + "/v1/nox/stats")
        self.memory = pick("memory", memory, "/memory/api")
        self.timeout = float(q.get("timeout", timeout))
        self.fast_timeout = float(q.get("fast_timeout", fast_timeout))
        self.first_frame_timeout = float(q.get("first_frame_timeout", first_frame_timeout))
        self.expect_tier = q.get("tier", expect_tier)
        self.mini_mode = q.get("mini", mini_mode)
        self.headers = dict(headers or {})
        if "token" in q:
            self.headers["Authorization"] = "Bearer " + q["token"]


def _conn(origin, timeout):
    u = urlsplit(origin)
    C = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    return C(u.hostname, u.port, timeout=timeout)


def call(cfg, method, path, body=None, headers=None, timeout=None):
    c = _conn(cfg.origin, timeout or cfg.timeout)
    try:
        h = {"Content-Type": "application/json", **cfg.headers, **(headers or {})}
        c.request(method, path, json.dumps(body).encode() if body is not None else None, h)
        r = c.getresponse()
        raw = r.read()
        try:
            return r.status, json.loads(raw or b"{}")
        except ValueError:
            return r.status, {"_raw": raw[:300].decode("utf-8", "replace")}
    finally:
        c.close()


def chat(cfg, session, text, extra_headers=None, history=None, max_tokens=120):
    msgs = list(history or []) + [{"role": "user", "content": text}]
    t0 = time.time()
    st, j = call(cfg, "POST", cfg.chat, {"messages": msgs, "stream": False, "nox_session": session, "max_tokens": max_tokens},
                 extra_headers)
    ans = ""
    try:
        ans = j["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        pass
    return {"status": st, "answer": ans, "nox": j.get("nox") or {}, "sec": round(time.time() - t0, 2), "raw": j}


def mem(cfg, op, **kw):
    return call(cfg, "POST", cfg.memory, dict(op=op, **kw))


def fact_id(j):
    for k in ("id", "ref"):
        if j.get(k):
            return j[k]
    f = j.get("fact") or {}
    return f.get("id") or f.get("ref")


def find_fact(cfg, nonce):
    st, j = mem(cfg, "search", query=nonce, k=10)
    hits = j.get("hits") or j.get("facts") or []
    for h in hits:
        txt = h.get("text") or h.get("snippet") or ""
        if nonce in txt:
            return {"id": h.get("ref") or h.get("id"), "text": txt, "hit": h}
    return None


class Stream:
    """Потоковый запрос в потоке: считает кадры, ловит request_id, фиксирует конец."""

    def __init__(self, cfg, session, text):
        self.cfg, self.frames, self.rid, self.done, self.err = cfg, 0, None, False, None
        self.finish_reason, self.t_last_frame, self.chars = None, None, 0
        self.t = threading.Thread(target=self._run, args=(session, text), daemon=True)
        self.t.start()

    def _run(self, session, text):
        c = _conn(self.cfg.origin, self.cfg.timeout)
        try:
            body = {"messages": [{"role": "user", "content": text}], "stream": True, "nox_session": session, "max_tokens": 2000}
            c.request("POST", self.cfg.chat, json.dumps(body).encode(), {"Content-Type": "application/json", **self.cfg.headers})
            r = c.getresponse()
            self.rid = r.getheader("X-NOX-Request-Id")
            buf = b""
            while True:
                line = r.readline()
                if not line:
                    break
                line = line.strip()
                if not line.startswith(b"data:"):
                    continue
                d = line[5:].strip()
                if d == b"[DONE]":
                    break
                try:
                    j = json.loads(d)
                except ValueError:
                    continue
                self.rid = self.rid or (j.get("nox") or {}).get("request_id")
                ch = (j.get("choices") or [{}])[0]
                piece = (ch.get("delta") or {}).get("content")
                if piece:
                    self.frames += 1
                    self.chars += len(piece)
                    self.t_last_frame = time.time()
                if ch.get("finish_reason"):
                    self.finish_reason = ch["finish_reason"]
        except Exception as e:  # обрыв при STOP — нормальный исход, ошибка фиксируется как данные
            self.err = "%s: %s" % (type(e).__name__, e)
        finally:
            self.done = True
            c.close()


def step_fast(cfg, ctx):
    r = chat(cfg, ctx["s1"], "Запомни кодовое слово %s. Ответь одним коротким предложением." % ctx["word"])
    n = r["nox"]
    tier = n.get("tier")
    ok = r["status"] == 200 and bool(r["answer"].strip()) and bool(n.get("request_id")) and r["sec"] <= cfg.fast_timeout
    if cfg.expect_tier and tier and tier != cfg.expect_tier:
        ok = False
    ctx["a1"] = r["answer"]
    return ok, {"http": r["status"], "sec": r["sec"], "tier": tier, "mode": n.get("mode"), "request_id": n.get("request_id"),
                "answer_head": r["answer"][:120], "limit_s": cfg.fast_timeout}


def step_mini(cfg, ctx):
    hist = None if cfg.mini_mode == "session" else [{"role": "user", "content": "Запомни кодовое слово %s." % ctx["word"]},
                                                      {"role": "assistant", "content": ctx["a1"]}]
    r = chat(cfg, ctx["s1"], "Какое кодовое слово я просил запомнить? Назови его.", {"X-NOX-Client": "mini"}, history=hist)
    ok = r["status"] == 200 and ctx["word"].lower() in r["answer"].lower()
    return ok, {"http": r["status"], "mode": cfg.mini_mode, "answer_head": r["answer"][:160], "expected": ctx["word"], "sec": r["sec"]}


def step_source(cfg, ctx):
    st, j = mem(cfg, "add", text="%s: любимый цвет мессира для проверки PV-01 — синий." % ctx["nonce"])
    ctx["fid"] = fact_id(j)
    f = find_fact(cfg, ctx["nonce"])
    if f and not ctx["fid"]:
        ctx["fid"] = f["id"]
    ok = bool(st == 200 and j.get("ok") and f and f["id"] and "синий" in f["text"])
    return ok, {"add_http": st, "add_ok": j.get("ok"), "fact_id": ctx["fid"], "found": bool(f), "text": f and f["text"][:120]}


def step_provenance(cfg, ctx):
    r = chat(cfg, ctx["s1"], "Какой любимый цвет мессира для проверки %s?" % ctx["nonce"])
    info = json.dumps(r["nox"].get("memory", ""), ensure_ascii=False)
    used = bool(ctx["fid"]) and str(ctx["fid"]) in info
    ok = r["status"] == 200 and "син" in r["answer"].lower() and used
    return ok, {"answer_head": r["answer"][:120], "fact_in_answer": "син" in r["answer"].lower(), "fact_id_listed_in_nox.memory": used,
                "nox.memory": info[:300],
                "gap": None if used else "шлюз не сообщает, какие факты попали в ответ (nox.memory без id факта) — см. ACT-07"}


def step_correct(cfg, ctx):
    st, j = mem(cfg, "correct", id=ctx["fid"], text="%s: любимый цвет мессира для проверки PV-01 — зелёный." % ctx["nonce"],
                reason="PV-01 правка")
    f = find_fact(cfg, ctx["nonce"])
    server_ok = st == 200 and j.get("ok") is True
    read_ok = bool(f and "зелён" in f["text"] and "синий" not in f["text"])
    return server_ok and read_ok, {"http": st, "server_ok": j.get("ok"), "readback_text": f and f["text"][:120],
                                   "note": "UI не вправе показывать правку, если server_ok != true (дефект nox-web-extras.js)"}


def step_refresh(cfg, ctx):
    f = find_fact(cfg, ctx["nonce"])  # новое соединение, нет клиентского кэша
    return bool(f and "зелён" in f["text"]), {"readback_text": f and f["text"][:120], "new_session": ctx["s2"]}


def step_answer(cfg, ctx):
    r = chat(cfg, ctx["s2"], "Какой любимый цвет мессира для проверки %s?" % ctx["nonce"])
    a = r["answer"].lower()
    return r["status"] == 200 and "зелён" in a and "синий" not in a, {"answer_head": r["answer"][:160], "session": ctx["s2"], "sec": r["sec"]}


def step_stop(cfg, ctx):
    s = Stream(cfg, ctx["s3"], LONG_Q)
    t0 = time.time()
    while time.time() - t0 < cfg.first_frame_timeout and not s.frames and not s.done:
        time.sleep(0.2)
    frames_before = s.frames
    rid = s.rid
    if not rid:
        return False, {"error": "нет request_id (заголовок X-NOX-Request-Id / nox.request_id)", "frames": frames_before, "stream_err": s.err}
    t_stop = time.time()
    st, j = call(cfg, "POST", cfg.stop, {"request_id": rid})
    stopped = st == 200 and j.get("stopped") is True and j.get("request_id") in (rid, None)
    gone, t_gone = False, None
    while time.time() - t_stop < 10:
        _, sj = call(cfg, "GET", cfg.stats)
        act = sj.get("active")
        ids = [a.get("id") if isinstance(a, dict) else a for a in (act or [])] if isinstance(act, list) else None
        if ids is not None and rid not in ids:
            gone, t_gone = True, round(time.time() - t_stop, 2)
            break
        if ids is None and isinstance(act, int) and act == 0:
            gone, t_gone = True, round(time.time() - t_stop, 2)
            break
        time.sleep(0.3)
    time.sleep(1.5)  # льготное окно: кадры «в полёте»
    snap1 = s.frames
    time.sleep(2.0)  # дальше тишина: новых кадров быть не должно
    silent = s.frames == snap1
    s.t.join(5)
    ok = frames_before > 0 and stopped and gone and silent and s.done
    return ok, {"request_id": rid, "frames_before_stop": frames_before, "stop_http": st, "stop_response": j, "removed_from_active_s": t_gone,
                "stream_ended": s.done, "frames_total": s.frames, "frames_after_stop_window": s.frames - frames_before,
                "finish_reason": s.finish_reason, "stream_err": s.err,
                "receipt_has_generated_count": any(k in j for k in ("tokens", "chars", "generated", "generated_chars")),
                "gap": None if frames_before else "0 кадров потока до STOP (известная проба 03:57: поток пуст)"}


STEPS = [("S1_fast_route", step_fast), ("S2_minichat_same_session", step_mini), ("S3_fact_source", step_source),
         ("S3b_provenance_in_answer", step_provenance), ("S4_correct_fact", step_correct), ("S5_refresh_readback", step_refresh),
         ("S6_answer_with_fix_new_dialog", step_answer), ("S7_stop_server_receipt", step_stop)]


def run(cfg, only=None):
    nonce = "pv01-" + secrets.token_hex(3)
    ctx = {"nonce": nonce, "word": "кедр" + secrets.token_hex(2), "s1": "pv01-a-" + nonce, "s2": "pv01-b-" + nonce, "s3": "pv01-c-" + nonce}
    res, t0 = [], time.time()
    try:
        for sid, fn in STEPS:
            if only and sid.split("_")[0] not in only:
                continue
            ts = time.time()
            try:
                ok, d = fn(cfg, ctx)
            except Exception as e:
                ok, d = False, {"exception": "%s: %s" % (type(e).__name__, e)}
            res.append({"step": sid, "ok": bool(ok), "sec": round(time.time() - ts, 2), "detail": d})
    finally:
        cleanup = None
        if ctx.get("fid"):
            try:
                st, j = mem(cfg, "delete", id=ctx["fid"], reason="PV-01 уборка")
                cleanup = {"http": st, "ok": j.get("ok")}
            except Exception as e:
                cleanup = {"error": str(e)}
    first_fail = next((r["step"] for r in res if not r["ok"]), None)
    return {"id": "ACT-PV01", "ok": bool(res) and first_fail is None, "first_broken_link": first_fail, "steps": res,
            "cleanup_test_fact": cleanup, "target": cfg.origin, "nonce": nonce, "sec": round(time.time() - t0, 1), "ts": time.time()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url")
    ap.add_argument("--base", default=os.environ.get("NOX_GATEWAY"))
    for k in ("memory", "chat", "stop", "stats"):
        ap.add_argument("--" + k)
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--fast-timeout", type=float, default=20)
    ap.add_argument("--first-frame-timeout", type=float, default=25)
    ap.add_argument("--expect-tier", default="fast")
    ap.add_argument("--mini-mode", choices=["session", "history"], default="session")
    ap.add_argument("--only", help="например S1,S2")
    ap.add_argument("--receipt")
    ns = ap.parse_args(argv)
    cfg = Cfg(url=ns.url, base=ns.base, memory=ns.memory, chat=ns.chat, stop=ns.stop, stats=ns.stats, timeout=ns.timeout,
              fast_timeout=ns.fast_timeout, first_frame_timeout=ns.first_frame_timeout, expect_tier=ns.expect_tier, mini_mode=ns.mini_mode)
    out = run(cfg, set(ns.only.split(",")) if ns.only else None)
    if ns.receipt:
        os.makedirs(os.path.dirname(ns.receipt) or ".", exist_ok=True)
        open(ns.receipt, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
