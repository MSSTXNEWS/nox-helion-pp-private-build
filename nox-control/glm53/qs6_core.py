"""NOX Быстрый запуск v6, блок «Мозг и чат»: роутер тиров, режимы, ETA, STOP, апстрим со стримом, сшивка двух тактов. Только stdlib."""
import json, os, re, socket, threading, time, uuid, hashlib, http.client
import math
from collections import deque
from urllib.parse import urlparse
import glm_profile as P

# ---------- конфиг (env / JSON) ----------
DEFAULT_MODES = {
    "fast": {"tier": "fast", "effort": None, "max_tokens": 512, "expected_tokens": 120, "two_stage": False},
    "auto": {"tier": "auto", "effort": None, "max_tokens": None, "expected_tokens": None, "two_stage": True},
    "deep": {"tier": "two_stage", "effort": "high", "max_tokens": 8192, "expected_tokens": 700, "two_stage": True},
    "max":  {"tier": "two_stage", "effort": "max", "max_tokens": 16384, "expected_tokens": 2500, "two_stage": True},
}
EXPECTED_BY_EFFORT = {"low": 250, "high": 700, "max": 2500}
DEFAULT_ROUTER = {"fast_max_words": 25, "deep_min_words": 120, "deep_min_chars": 1500,
                  "think_re": r"подума\w*|глубок\w*|тщательно|детально|подробн\w*|think (?:hard|deeply|carefully)|в\s+деталях",
                  "greeting_max_words": 4}

def _load_json(v):
    if not v: return {}
    v = v.strip()
    try:
        if v.startswith("{"): return json.loads(v)
        with open(v, encoding="utf-8") as f: return json.load(f)
    except Exception:
        return {}

class Cfg:
    def __init__(self, **kw):
        e = os.environ.get
        fast = e("NOX_FAST_UPSTREAM", "http://127.0.0.1:8083")
        self.deep_url = e("NOX_UPSTREAM", "http://127.0.0.1:8081")
        self.fast_url = "" if fast.strip().lower() in ("", "off", "none", "0") else fast
        self.fast_model = e("NOX_FAST_MODEL", "fast")
        self.host = e("NOX_LISTEN_HOST", "127.0.0.1"); self.port = int(e("NOX_LISTEN_PORT", "8082"))
        self.fast_sentences = int(e("NOX_FAST_FIRST_SENTENCES", "2"))
        self.fast_first_max_tokens = int(e("NOX_FAST_FIRST_MAX_TOKENS", "120"))
        self.ping_s = float(e("NOX_PING_S", "5"))
        self.fast_cooldown_s = float(e("NOX_FAST_COOLDOWN_S", "20"))
        self.deep_timeout = float(e("NOX_DEEP_TIMEOUT", "900")); self.fast_timeout = float(e("NOX_FAST_TIMEOUT", "30"))
        self.connect_timeout = float(e("NOX_CONNECT_TIMEOUT", "5"))
        self.tps_default = {"deep": float(e("NOX_DEFAULT_TPS_DEEP", "1.5")), "fast": float(e("NOX_DEFAULT_TPS_FAST", "40"))}
        self.two_stage = e("NOX_TWO_STAGE", "1") not in ("0", "false", "off")
        self.session_summary = e("NOX_SESSION_SUMMARY", "")
        self.router = dict(DEFAULT_ROUTER); self.router.update(_load_json(e("NOX_ROUTER_JSON", "")))
        self.modes = {k: dict(v) for k, v in DEFAULT_MODES.items()}
        for k, v in _load_json(e("NOX_MODES_JSON", "")).items():
            if k in self.modes and isinstance(v, dict): self.modes[k].update(v)
        for k, v in kw.items(): setattr(self, k, v)

# ---------- D04-03 роутер быстрый/глубокий ----------
def route_tier(messages, cfg, tools=False, chalie=None):
    """-> {tier: fast|deep|two_stage, reason, features}. fast: малая модель; deep: только GLM; two_stage: быстрое начало + GLM."""
    r = cfg.router
    text = P.last_user_text(messages)
    words = len(text.split()); chars = len(text)
    code = bool(P.CODE_RE.search(text)); think = bool(re.search(r.get("think_re", ""), text, re.I)) if r.get("think_re") else False
    reason_kw = bool(P.REASON_RE.search(text))
    f = {"words": words, "chars": chars, "code": code, "think": think, "reasoning": reason_kw, "tools": tools, "chalie": chalie}
    def R(t, why): return {"tier": t, "reason": why, "features": f}
    if tools: return R("deep", "tools")
    if code: return R("deep", "code")
    if chars > r["deep_min_chars"] or words >= r["deep_min_words"]: return R("deep", "long")
    if think: return R("two_stage", "think_keyword")
    if reason_kw or words > r["fast_max_words"]: return R("two_stage", "reasoning_or_medium")
    return R("fast", "simple")

def plan_request(body, cfg, tools=False, chalie=None, fast_ok=True):
    """Режим -> тир, effort, max_tokens. Возвращает dict плана."""
    mode = body.get("nox_mode") or "auto"
    if mode not in cfg.modes: mode = "auto"
    m = cfg.modes[mode]
    msgs = body.get("messages") or []
    rt = None
    tier = m["tier"]
    if tier == "auto":
        rt = route_tier(msgs, cfg, tools, chalie); tier = rt["tier"]
    elif tools:
        tier = "deep"
    if not cfg.two_stage and tier == "two_stage": tier = "deep"
    if tier in ("two_stage", "fast") and not fast_ok:
        note = "fast_unavailable"
        tier = "deep"
    else: note = None
    if tier == "two_stage" and not m.get("two_stage", True): tier = "deep"
    effort = None
    if tier in ("deep", "two_stage"):
        effort = m.get("effort") or P.pick_effort(P.last_user_text(msgs), body.get("reasoning_effort"))
    req_mt = body.get("max_tokens")
    mt = m.get("max_tokens")
    expected = m.get("expected_tokens") or (EXPECTED_BY_EFFORT.get(effort) if effort else 120)
    if mt is None and effort: mt = P.MAX_TOKENS_MIN[effort]
    if req_mt and mode in ("auto",) and mt is None: mt = req_mt
    return {"mode": mode, "tier": tier, "effort": effort, "max_tokens": mt, "expected_tokens": expected, "route": rt, "note": note}

# ---------- D04-04 измеряемая скорость и ETA ----------
class SpeedMeter:
    def __init__(self, cfg, window=20):
        self.cfg = cfg; self.w = window; self.s = {"deep": deque(maxlen=window), "fast": deque(maxlen=window)}; self.lock = threading.Lock()
    def record(self, tier, tokens, seconds):
        if tokens >= 3 and seconds > 0.05:
            with self.lock: self.s[tier].append((tokens, seconds))
    def tps(self, tier):
        with self.lock:
            d = list(self.s[tier])
        if d: return sum(t for t, _ in d) / sum(s for _, s in d), "measured:%d" % len(d)
        return self.cfg.tps_default[tier], "default"
    def eta(self, plan):
        """eta_s полного ответа и eta_first_s (первый такт). Токены включают размышления GLM."""
        out = {}
        if plan["tier"] == "fast":
            t, b = self.tps("fast"); out = {"eta_s": round(0.3 + plan["expected_tokens"] / t, 1), "basis": b}
        else:
            t, b = self.tps("deep"); out = {"eta_s": round(2.0 + plan["expected_tokens"] / t, 1), "basis": b}
            if plan["tier"] == "two_stage":
                ft, _ = self.tps("fast"); out["eta_first_s"] = round(0.3 + 30 / ft, 1)
        return out
    def snapshot(self):
        return {k: {"tps": round(self.tps(k)[0], 2), "basis": self.tps(k)[1]} for k in self.s}

class CacheStats:
    def __init__(self): self.lock = threading.Lock(); self.cached = 0; self.prompt = 0; self.n = 0
    def record(self, cached, prompt_total):
        with self.lock: self.cached += cached or 0; self.prompt += prompt_total or 0; self.n += 1
    def snapshot(self):
        with self.lock: return {"tokens_cached": self.cached, "prompt_tokens": self.prompt, "requests": self.n, "hit_ratio": round(self.cached / self.prompt, 3) if self.prompt else None}

def cache_from(obj):
    """Из ответа/последнего чанка llama-server: (tokens_cached, prompt_total)."""
    t = (obj or {}).get("timings") or {}
    cached = obj.get("tokens_cached") if isinstance(obj, dict) and obj.get("tokens_cached") is not None else t.get("cache_n")
    prompt_n = t.get("prompt_n")
    if cached is None and prompt_n is None: return None
    return (cached or 0), (cached or 0) + (prompt_n or 0)

def engine_metrics(timings):
    """Use llama-server token counts and phase times; SSE frames are not tokens."""
    if not isinstance(timings, dict):
        return {}
    measures = {}
    for phase, field in (("prefill", "prompt"), ("decode", "predicted")):
        count = timings.get(field + "_n")
        duration = timings.get(field + "_ms")
        if (type(count) is int and count >= 0 and type(duration) in (int, float)
                and math.isfinite(duration) and duration > 0):
            measures[phase] = {
                "tokens": count, "ms": duration,
                "tokens_per_second": round(count * 1000 / duration, 3),
            }
    return measures

# ---------- D04-01 / D15 STOP ----------
class Req:
    def __init__(self):
        self.id = uuid.uuid4().hex[:16]; self.cancelled = threading.Event(); self.lock = threading.Lock(); self.conns = []; self.t0 = time.time()
    def add(self, c):
        with self.lock: self.conns.append(c)
        if self.cancelled.is_set(): self.close(c)
    @staticmethod
    def close(c):
        try:
            if c.sock is not None:
                try: c.sock.shutdown(socket.SHUT_RDWR)
                except Exception: pass
            c.close()
        except Exception: pass
    def cancel(self):
        self.cancelled.set()
        with self.lock: cs = list(self.conns)
        for c in cs: self.close(c)

class Registry:
    def __init__(self): self.lock = threading.Lock(); self.d = {}
    def new(self):
        r = Req()
        with self.lock: self.d[r.id] = r
        return r
    def done(self, r):
        with self.lock: self.d.pop(r.id, None)
    def stop(self, rid):
        with self.lock: r = self.d.get(rid)
        if not r: return False
        r.cancel(); return True
    def active(self):
        with self.lock: return list(self.d)

class UpstreamError(Exception):
    pass

def open_upstream(base, path, body, req, connect_timeout, read_timeout):
    """Открывает POST к llama-server через http.client; соединение регистрируется в req для STOP."""
    u = urlparse(base)
    c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=connect_timeout)
    try:
        c.connect()
        c.sock.settimeout(read_timeout)
        req.add(c)
        c.request("POST", (u.path.rstrip("/") + path), body=json.dumps(body, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
        r = c.getresponse()
    except Exception as e:
        Req.close(c); raise UpstreamError("%s: %s" % (type(e).__name__, e))
    if r.status != 200:
        data = r.read(500); Req.close(c); raise UpstreamError("HTTP %d %s" % (r.status, data[:200].decode("utf-8", "replace")))
    return c, r

def iter_sse(resp):
    while True:
        line = resp.readline()
        if not line: return
        line = line.strip()
        if line.startswith(b"data:"):
            yield line[5:].strip().decode("utf-8", "replace")

# ---------- сшивка ----------
class ThinkFilter:
    """Убирает <think>..</think> из потока content."""
    def __init__(self): self.buf = ""; self.inside = False
    def feed(self, s):
        self.buf += s; out = ""
        while True:
            if self.inside:
                i = self.buf.find("</think>")
                if i < 0: self.buf = self.buf[-8:]; return out
                self.buf = self.buf[i + 8:]; self.inside = False
            else:
                i = self.buf.find("<think>")
                if i >= 0: out += self.buf[:i]; self.buf = self.buf[i + 7:]; self.inside = True; continue
                keep = 0
                for k in range(min(6, len(self.buf)), 0, -1):
                    if "<think>".startswith(self.buf[-k:]): keep = k; break
                out += self.buf[:len(self.buf) - keep]; self.buf = self.buf[len(self.buf) - keep:]; return out
    def flush(self):
        out = "" if self.inside else self.buf; self.buf = ""; return out

_SENT_END = re.compile(r"[.!?…]+[\"»)\]]*(?:\s+|$)")
def _norm(s): return re.sub(r"[\W_]+", " ", s.casefold().replace("ё", "е")).strip()
def split_sentences(t): return [s for s in re.split(r"(?<=[.!?…])\s+", t.strip()) if s]

def _is_dup(sent, fast_sents):
    n = _norm(sent)
    if not n: return True
    import difflib
    return any(n == _norm(f) or difflib.SequenceMatcher(None, n, _norm(f)).ratio() >= 0.85 for f in fast_sents)

class Stitcher:
    """Глубокий такт: отбрасывает ведущие предложения, повторяющие быстрый такт; остальное идёт без задержки."""
    def __init__(self, fast_text):
        self.fs = split_sentences(fast_text); self.buf = ""; self.passthrough = not self.fs; self.dropped = 0
    def _drain(self, final):
        out = ""
        while self.buf and not self.passthrough:
            m = _SENT_END.search(self.buf)
            if m and (m.end() < len(self.buf) or final):
                sent = self.buf[:m.end()]
                if _is_dup(sent, self.fs): self.dropped += 1; self.buf = self.buf[m.end():].lstrip()
                else: self.passthrough = True
            elif len(self.buf) > 240 or (final and not m):
                if final and _is_dup(self.buf, self.fs): self.dropped += 1; self.buf = ""
                else: self.passthrough = True
            else: break
        if self.passthrough: out, self.buf = self.buf, ""
        return out
    def feed(self, s):
        if self.passthrough: return s
        self.buf += s; return self._drain(False)
    def finish(self):
        if self.passthrough: return ""
        return self._drain(True)

# ---------- промпты (D02-08/09: префикс фиксирован, динамика в хвосте) ----------
FAST_SUFFIX = "\nТы быстрый ответчик. Отвечай кратко и по делу, по-русски."
FIRST_TAIL = "\n\n[Режим первого такта: ответь только 1-2 короткими предложениями: суть или подтверждение. Без списков и подробностей, они придут следом.]"
DEEP_TAIL = "\n\n[Короткое вступление уже показано пользователю. Не повторяй его и не подтверждай заново, сразу дай глубину: детали, шаги, нюансы.]"

def _strip_nox(body):
    b = {k: v for k, v in body.items() if not k.startswith("nox_") or k in ("nox_facts", "nox_system")}
    return b

def prefix_hash():
    return hashlib.sha1((P.persona() + "|" + FAST_SUFFIX).encode()).hexdigest()[:12]

def _append_tail(msgs, tail):
    msgs = list(msgs)
    if msgs and msgs[-1].get("role") == "user" and isinstance(msgs[-1].get("content"), str):
        msgs[-1] = dict(msgs[-1], content=msgs[-1]["content"] + tail)
    return msgs

def build_deep(body, plan, cfg, stream, after_fast=False):
    b = _strip_nox(body); b["stream"] = stream
    b["reasoning_effort"] = plan["effort"]
    req, effort = P.build_request(b)
    if plan["max_tokens"]: req["max_tokens"] = min(plan["max_tokens"], P.CTX_LIMIT - 512)
    if after_fast: req["messages"] = _append_tail(req["messages"], DEEP_TAIL)
    req["cache_prompt"] = True
    if stream: req["stream_options"] = {"include_usage": True}
    return req, effort

def build_fast(body, plan, cfg, stream, first_part):
    b = _strip_nox(body); facts = b.pop("nox_facts", None); soul = b.pop("nox_system", None); b.pop("reasoning_effort", None)
    msgs = P.clean_history(list(b.get("messages") or []), keep_reasoning=False)
    sysmsg = {"role": "system", "content": (soul.strip() if isinstance(soul, str) and soul.strip() else P.persona()) + FAST_SUFFIX}
    msgs = [sysmsg] + [m for m in msgs if m.get("role") != "system"]
    block = P.compact_facts(facts)
    if block and msgs[-1].get("role") == "user" and isinstance(msgs[-1].get("content"), str):
        msgs[-1] = dict(msgs[-1], content=block + "\n\n" + msgs[-1]["content"])
    if first_part: msgs = _append_tail(msgs, FIRST_TAIL)
    mt = cfg.fast_first_max_tokens if first_part else (plan["max_tokens"] or 512)
    req = {"model": cfg.fast_model, "messages": msgs, "stream": stream, "max_tokens": mt, "temperature": 0.7, "top_p": 0.95,
           "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False}}
    if stream: req["stream_options"] = {"include_usage": True}
    return req

# ---------- поток от апстрима в очередь ----------
def pump(cfg, meter, cache, tier, base, body, req, q, max_sentences=None):
    """Читает SSE апстрима, кладёт ("delta", текст) и в конце ("end", info) или ("error", (сообщение, был_ли_текст))."""
    text = ""; first_generated = None; first_visible = None; timings = None; usage = None
    finish = None; framed_end = False; saw_tool_call = False; conn = None
    tf = ThinkFilter(); start = time.monotonic()
    try:
        conn, resp = open_upstream(base, "/v1/chat/completions", body, req, cfg.connect_timeout, cfg.fast_timeout if tier == "fast" else cfg.deep_timeout)
        for ev in iter_sse(resp):
            if req.cancelled.is_set(): break
            if ev == "[DONE]":
                framed_end = True
                break
            try: o = json.loads(ev)
            except Exception: continue
            if o.get("error"):
                error = o["error"]
                detail = error.get("message") if isinstance(error, dict) else str(error)
                raise UpstreamError(detail or "upstream stream error")
            if o.get("timings"): timings = o["timings"]
            if o.get("usage"): usage = o["usage"]
            ch = (o.get("choices") or [None])[0] or {}
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]
                if finish == "error":
                    raise UpstreamError("upstream stream finished with an error")
            d = ch.get("delta") or {}
            piece = d.get("content") or ""; reas = d.get("reasoning_content") or ""
            saw_tool_call = saw_tool_call or bool(d.get("tool_calls") or d.get("function_call"))
            if first_generated is None and (piece or reas):
                first_generated = time.monotonic() - start
            vis = tf.feed(piece) if piece else ""
            if vis:
                if first_visible is None and vis.strip():
                    first_visible = time.monotonic() - start
                text += vis; q.put((tier, "delta", vis))
                if max_sentences and len(re.findall(r"[.!?…]+(?=\s|$)", text)) >= max_sentences:
                    finish = "nox_sentence_limit"; break
        if req.cancelled.is_set(): q.put((tier, "end", {"cancelled": True, "text": text})); return
        if finish != "nox_sentence_limit" and (not framed_end or not finish):
            raise UpstreamError("upstream stream ended without a complete terminal frame")
        tail = tf.flush()
        if tail:
            if first_visible is None and tail.strip():
                first_visible = time.monotonic() - start
            text += tail; q.put((tier, "delta", tail))
        if not text.strip() and not saw_tool_call:
            raise UpstreamError("upstream finished without visible answer or tool calls")
        phases = engine_metrics(timings)
        decode = phases.get("decode")
        n = decode["tokens"] if decode else (usage or {}).get("completion_tokens")
        if decode and finish != "nox_sentence_limit":
            meter.record(tier, decode["tokens"], decode["ms"] / 1000)
        cs = cache_from({"timings": timings}) if timings else None
        if cs and tier == "deep": cache.record(*cs)
        if finish == "nox_sentence_limit" and conn is not None: Req.close(conn)     # лишнее не генерируем
        q.put((tier, "end", {"text": text, "tokens": n,
                             "ttft_s": round(first_visible, 3) if first_visible is not None else None,
                             "first_generated_s": round(first_generated, 3) if first_generated is not None else None,
                             "timings": phases, "finish": finish,
                             "cache": {"tokens_cached": cs[0], "prompt_tokens": cs[1]} if cs else None}))
    except Exception as e:
        if req.cancelled.is_set(): q.put((tier, "end", {"cancelled": True, "text": text}))
        else: q.put((tier, "error", (str(e) or type(e).__name__, bool(text), text)))
    finally:
        if conn is not None: Req.close(conn)
