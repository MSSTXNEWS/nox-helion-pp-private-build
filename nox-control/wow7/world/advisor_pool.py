#!/usr/bin/env python3
"""advisor_pool: пул БЕСПЛАТНЫХ советников с ротацией, лимитами, кулдауном, таймаутами, кэшем и карантином ответов.

Stdlib only (gradio_client - опционально, для публичных HF Spaces). Ключи ТОЛЬКО из env (api_key_env). Бюджет 0:
нет ключа -> провайдер пропускается; лимиты rpm/daily считаются локально и пока не исчерпаны - пользуемся; 429/402 -> кулдаун.
Исходящий текст чистится от секретов и путей. Провайдеры с trains_on_data=true получают только privacy="public".
Ответ советника - ДАННЫЕ: обрезан, очищен, помечен «мнение советника, не NOX», подозрительные инструкции вырезаны.
НЕ используется DuckDuckGo AI Chat: условия duck.ai запрещают automated querying. SearXNG остаётся в nox_advisors.py.
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import hashlib
import json

import statefile
import datafence
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
LABEL = "мнение советника, не NOX"
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")
_INJ = re.compile(r"(ignore (all |the )?(previous|above)|disregard .{0,20}instructions|игнорируй .{0,20}(инструкц|правил)|"
                  r"забудь .{0,20}(инструкц|правил)|rm -rf|curl [^ ]+ \| ?(ba)?sh|\bsudo\b)", re.I)
_SECRETS = [re.compile(p) for p in (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", r"\b(?:sk|pk|rk|gsk)[-_][A-Za-z0-9_\-]{16,}",
    r"\bgh[pousr]_[A-Za-z0-9]{20,}", r"\bhf_[A-Za-z0-9]{20,}", r"\bAIza[0-9A-Za-z_\-]{30,}",
    r"(?i)\b(?:api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*['\"]?(?:Bearer\s+)?[^\s'\",;]{6,}",
    r"(?i)\bBearer\s+[A-Za-z0-9._\-]{16,}")]
_PATHS = [re.compile(p) for p in (r"(?<![\w.])/(?:home|root|etc|var|opt|srv|mnt|tmp|usr)/[^\s'\"`,;:)]*", r"(?<![\w.])~/[^\s'\"`,;:)]*")]


class PoolError(Exception):
    pass


def sanitize_outgoing(text):
    for rx in _SECRETS:
        text = rx.sub("[REDACTED_SECRET]", text)
    for rx in _PATHS:
        text = rx.sub("[PATH]", text)
    return text


def quarantine_answer(text, cap=6000):
    """-> (текст, suspicious). Только данные: управляющие символы и «инструкции» вырезаны."""
    text = _CTRL.sub("", text or "")
    sus = bool(_INJ.search(text))
    if sus:
        text = _INJ.sub("[фрагмент вырезан]", text)
    return text[:cap], sus


def load_config(path=None):
    with open(path or os.path.join(HERE, "advisors_free.json"), encoding="utf-8") as f:
        return json.load(f)


# ---------- транспорты ----------
def http_openai(p, messages, timeout, key):
    """POST {url}/chat/completions. Возвращает текст. Исключения PoolError(code) с .retry_after."""
    payload = {"model": p["model"], "messages": messages, p.get("token_param", "max_tokens"): p.get("max_tokens", 700), "temperature": 0.3}
    payload.update(p.get("extra_body") or {})   # ADV: напр. OpenRouter provider.max_price=0, allow_fallbacks=false
    body = json.dumps(payload).encode()
    req = urllib.request.Request(p["url"].rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read().decode("utf-8"))
        return j["choices"][0]["message"]["content"] or ""
    except urllib.error.HTTPError as e:
        err = PoolError("http %d" % e.code)
        err.code = e.code
        try:
            err.retry_after = float(e.headers.get("Retry-After", 0) or 0)
        except ValueError:
            err.retry_after = 0
        raise err
    except (urllib.error.URLError, OSError, KeyError, ValueError, IndexError) as e:
        err = PoolError("net: %s" % str(e)[:80])
        err.code = 0
        err.retry_after = 0
        raise err


def list_models(p, key, timeout=15):
    req = urllib.request.Request(p["url"].rstrip("/") + "/models", headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        j = json.loads(r.read().decode("utf-8"))
    return [m["id"] for m in j.get("data", []) if isinstance(m, dict) and "id" in m]


def gradio_call(p, messages, timeout, key):
    try:
        from gradio_client import Client
    except ImportError:
        raise PoolError("gradio_client not installed")
    if not p.get("space"):
        raise PoolError("space not set")
    cl = Client(p["space"], hf_token=key or None, httpx_kwargs={"timeout": timeout})
    return str(cl.predict(messages[-1]["content"], api_name=p.get("api_name", "/chat")))


# ---------- пул ----------
class Pool:
    def __init__(self, config=None, state_path=None, env=None, clock=time.time, transport=None, models_fn=None):
        self.cfg = config or load_config()
        self.providers = sorted([p for p in self.cfg["providers"] if p.get("enabled", True)], key=lambda p: p.get("prio", 50))
        self.env = os.environ if env is None else env
        self.clock = clock
        self.transport = transport
        self.models_fn = models_fn or list_models
        self.state_path = state_path or os.environ.get("NOX_ADVPOOL", "/root/nox/state/advisor_pool.json")
        self.ttl = self.cfg.get("cache_ttl_s", 86400)
        self.cap = self.cfg.get("max_answer", 6000)
        self.lock = threading.Lock()
        self.st = {"daily": {}, "cool": {}, "cache": {}, "recent": {}}
        try:
            with open(self.state_path, encoding="utf-8") as f:
                self.st.update(json.load(f))
        except (OSError, ValueError):
            pass
        self._models = {}

    # учёт
    def _day(self):
        return time.strftime("%Y-%m-%d", time.gmtime(self.clock()))

    def _save(self):
        try:
            statefile.save(self.state_path, self.st)
        except OSError:
            pass

    def _used_today(self, name):
        return self.st["daily"].get(name, {}).get(self._day(), 0)

    def _rpm_ok(self, p):
        now = self.clock()
        rec = [t for t in self.st["recent"].get(p["name"], []) if now - t < 60]
        self.st["recent"][p["name"]] = rec
        return len(rec) < p.get("rpm", 10)

    def available(self, privacy="private"):
        """Провайдеры, которым прямо сейчас можно слать запрос (по порядку приоритета)."""
        now, out = self.clock(), []
        for p in self.providers:
            if p["kind"] == "openai" and not self.env.get(p.get("api_key_env", "")):
                continue
            if p.get("trains_on_data") and privacy != "public":
                continue
            if self.st["cool"].get(p["name"], 0) > now:
                continue
            if self._used_today(p["name"]) >= p.get("daily", 50):
                continue
            if not self._rpm_ok(p):
                continue
            out.append(p)
        return out

    def _resolve_model(self, p, key):
        if p.get("model"):
            return p["model"]
        if p["name"] in self._models:
            return self._models[p["name"]]
        ids = self.models_fn(p, key)
        rx = re.compile(p.get("model_filter", "."))
        pick = [i for i in ids if rx.search(i)]
        if not pick:
            raise PoolError("no model matches")
        self._models[p["name"]] = pick[0]
        return pick[0]

    def _key(self, prompt, system):
        return hashlib.sha256((system + "\x00" + prompt).encode()).hexdigest()

    def ask(self, prompt, system="", privacy="private", role=None, use_cache=True):
        """-> {"ok","text","provider","cached","suspicious","label"} или {"ok":False,"error":...}. Перебирает провайдеров по приоритету."""
        prompt_s = sanitize_outgoing(prompt)
        system_s = sanitize_outgoing(system)
        ck = self._key(prompt_s, system_s)
        with self.lock:
            hit = self.st["cache"].get(ck)
            if use_cache and hit and self.clock() - hit["t"] < self.ttl and (privacy == "public" or hit.get("privacy") == privacy):
                return {"ok": True, "text": hit["text"], "provider": hit["provider"], "cached": True,
                        "framed": datafence.data_frame(hit["text"], "советник:" + hit["provider"], trust="низкое", limit=self.cap),
                        "suspicious": hit["sus"], "label": LABEL}
            cands = [p for p in self.available(privacy) if role in (None, p.get("role"), "general") or p.get("role") == "fallback"]
        errors = {}
        msgs = ([{"role": "system", "content": system_s}] if system_s else []) + [{"role": "user", "content": prompt_s}]
        for p in cands:
            key = self.env.get(p.get("api_key_env", ""), "")
            with self.lock:
                self.st["recent"].setdefault(p["name"], []).append(self.clock())
                d = self.st["daily"].setdefault(p["name"], {})
                d[self._day()] = d.get(self._day(), 0) + 1
            try:
                if self.transport:
                    raw = self.transport(p, msgs, p.get("timeout_s", 60))
                elif p["kind"] == "gradio":
                    raw = gradio_call(p, msgs, p.get("timeout_s", 120), key)
                else:
                    pp = dict(p, model=self._resolve_model(p, key))
                    raw = http_openai(pp, msgs, p.get("timeout_s", 60), key)
            except PoolError as e:
                code = getattr(e, "code", 0)
                ra = getattr(e, "retry_after", 0) or 0
                cool = ra if ra else (3600 if code in (401, 402, 403) else 300 if code == 429 else 60)
                with self.lock:
                    self.st["cool"][p["name"]] = self.clock() + cool
                    self._save()
                errors[p["name"]] = str(e)[:80]
                continue
            text, sus = quarantine_answer(raw, self.cap)
            if not text.strip():
                errors[p["name"]] = "empty"
                continue
            with self.lock:
                self.st["cache"][ck] = {"t": self.clock(), "text": text, "provider": p["name"], "sus": sus, "privacy": privacy}
                self._gc()
                self._save()
            return {"ok": True, "text": text, "provider": p["name"], "cached": False, "suspicious": sus, "label": LABEL,
                    "framed": datafence.data_frame(text, "советник:" + p["name"], trust="низкое", limit=self.cap)}   # в промпт - только framed
        with self.lock:
            self._save()
        return {"ok": False, "error": "no advisor available", "errors": errors}

    def _gc(self, max_entries=500):
        c = self.st["cache"]
        now = self.clock()
        for k in [k for k, v in c.items() if now - v["t"] > self.ttl]:
            del c[k]
        if len(c) > max_entries:
            for k, _ in sorted(c.items(), key=lambda x: x[1]["t"])[:len(c) - max_entries]:
                del c[k]

    def status(self):
        now = self.clock()
        return {p["name"]: {"key": bool(self.env.get(p.get("api_key_env", ""))) or p["kind"] != "openai",
                            "used_today": self._used_today(p["name"]), "daily": p.get("daily"),
                            "cooldown_s": max(0, int(self.st["cool"].get(p["name"], 0) - now)),
                            "trains_on_data": bool(p.get("trains_on_data"))} for p in self.providers}

    def second_opinion(self, prompt, n=2, privacy="private"):
        """Мнения от до n РАЗНЫХ советников (кэш выключен), для сверки. Ответы - данные."""
        got, used = [], set()
        for _ in range(n):
            with self.lock:
                avail = [p for p in self.available(privacy) if p["name"] not in used]
            if not avail:
                break
            r = self._ask_one(avail[0], prompt, privacy)
            used.add(avail[0]["name"])
            if r.get("ok"):
                got.append(r)
        return got

    def _ask_one(self, p, prompt, privacy):
        saved = self.providers
        self.providers = [p]
        try:
            return self.ask(prompt, privacy=privacy, use_cache=False)
        finally:
            self.providers = saved


if __name__ == "__main__":
    pool = Pool()
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print(json.dumps(pool.status(), ensure_ascii=False, indent=1))
    elif len(sys.argv) > 1:
        print(json.dumps(pool.ask(" ".join(sys.argv[1:]), privacy="public"), ensure_ascii=False))
    else:
        print("usage: advisor_pool.py status | <public question>")
