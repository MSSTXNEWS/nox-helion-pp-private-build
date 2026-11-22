"""Хотфикс живого чата (самодостаточный, без файлов пакета): служебное -> nox_phase, пофразовый фильтр ответа,
внутренний блок состояния только на вопросах о состоянии. usage: hf_patch_web.py SRC DST"""
import re, sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()
if "NOXHF" in s:
    open(dst, "w", encoding="utf-8").write(s); print("already NOXHF"); sys.exit(0)
def rep(old, new, must=True):
    global s
    if old not in s:
        if must: sys.exit("MISSING: " + old[:80])
        print("skip:", old[:50]); return
    s = s.replace(old, new, 1)
imp = r'''# NOXHF: фильтр ответа и классификатор интента (самодостаточный)
import re as _hre
_SERVICE_RE = _hre.compile(r"Глубокий ответ|готовлю в фоне|\(задача\s*t?\d+|результат появится|Быстрый слой|быстрым слоем|повтори(те)? запрос|GLM\s*занят|</?think>|⏳|🧠\s*GLM", _hre.I)
_TEMPLATE_RE = _hre.compile(r"Жду твой ввод|Пустота в очереди|Что хочешь\s*[:—-]|→\s*\S+.*→|Очередь пуста", _hre.I)
_TELE_RE = [_hre.compile(p, _hre.I) for p in (r"\bGPU\b|видеокарт|VRAM", r"ток/с|tok/s|t/s", r"\d+\s*%", r"\d+\s*°C|\d+\s*ГБ|\d+\s*GB", r"очеред|задач[аи]?\s*t?\d+|диспетчер")]
_GREET = _hre.compile(r"^\s*(привет\w*|здравствуй\w*|здорово|хай|добр(ый|ое|ого)\s+\w+|салют|приветствую|hello|hi|hey|ку|йо)[\s!.,?)(:-]*(нокс|nox|мессир|создатель)?[\s!.,?)(:-]*$", _hre.I)
_STATUS = _hre.compile(r"как\s+(ты|дела|сервер|ты\s+себя)|состояни|статус|телеметр|нагрузк|gpu|видеокарт|vram|сервер|ток/с|скорост|диск|памят[ьи]\s+(занят|свобод)|очеред|что\s+с\s+тобой|чем\s+занят|что\s+делаеш|на\s+чём\s+работаеш|какая\s+модель|где\s+ты", _hre.I)
def _intent(t):
    t = (t or "").strip()
    if _GREET.match(t): return "greeting"
    if _STATUS.search(t): return "telemetry_q"
    return "smalltalk" if len(t) <= 25 else "other"
_NOXHF_LINE = ("Никогда не пересказывай блок внутреннего состояния и телеметрию, если Создатель прямо не спросил о состоянии/сервере. "
               "На приветствие — 1–3 живые фразы. Не предлагай списков «Что хочешь: →…».")
_SAFE = {"greeting": ("Привет, мессир. Я здесь.", "На связи, мессир. Что у тебя?", "Слушаю тебя, мессир.", "Здравствуй, мессир. Рад тебя слышать."),
         "other": ("Мессир, ответ сейчас не сложился; запись в журнале.",)}
_SAFE["smalltalk"] = _SAFE["greeting"]
_safe_n = [0]
def _safe(intent):
    b = _SAFE.get(intent) or _SAFE["other"]; _safe_n[0] += 1; return b[_safe_n[0] % len(b)]
def _bad_sentence(x, intent):
    if _SERVICE_RE.search(x) or _TEMPLATE_RE.search(x): return True
    if intent != "telemetry_q":
        hits = sum(1 for r in _TELE_RE if r.search(x))
        if hits >= 2 or (hits and intent in ("greeting", "smalltalk")): return True
    return False
def _strip(t, intent="other"):
    out = [x for x in _hre.split(r"(?<=[.!?…])\s+|\n+", t or "") if x and x.strip() and not _bad_sentence(x, intent)]
    return " ".join(out).strip(), False
class _SG:
    """Пофразовый шлюз потока: держит фразу до конца предложения, плохие роняет; приветствие — не больше 3 фраз."""
    def __init__(self, intent): self.i, self.buf, self.n, self.dropped = intent, "", 0, []
    def _gate(self, x):
        if not x.strip(): return [x] if x else []
        if _bad_sentence(x.strip(), self.i): self.dropped.append(x.strip()[:60]); return []
        if self.i in ("greeting", "smalltalk") and self.n >= 3: return []
        self.n += 1; return [x]
    def feed(self, p):
        self.buf += p; out = []
        while True:
            m = _hre.search(r"(?<=[.!?…])[\"»)]*\s|\n", self.buf); cut = m.end() if m else None
            if cut is None and len(self.buf) > 400:
                k = self.buf.find(" ", 400); cut = k + 1 if k != -1 else None
            if cut is None: break
            out += self._gate(self.buf[:cut]); self.buf = self.buf[cut:]
        return out
    def flush(self):
        o = self._gate(self.buf) if self.buf.strip() else []; self.buf = ""; return o
'''
m = re.search(r"^_MSK = .*$", s, re.M); assert m, "no _MSK"
s = s[:m.start()] + imp + s[m.start():]
s, n0 = re.subn(r'"content": "🧠[^"]*"', '"content": "", "nox_phase": {"phase": "deep_start"}', s)
print("deep_start:", n0)
s, n = re.subn(r'^(\s*)out\(\{"model": TAG, "message": \{"role": "assistant", "content": "⏳ Глубокий ответ.*$',
    r'\1out({"model": TAG, "message": {"role": "assistant", "content": ""}, "done": False, "nox_phase": {"phase": "deep_queued", "task": str(jid), "ahead": ahead}})', s, flags=re.M)
print("deep_queued lines:", n)
rep('content=_self_summary() + _user_text)', 'content=((_self_summary() if _intent(_user_text) == "telemetry_q" else "") + _user_text))')
rep('''        txt = self._fast_text(req) or "Быстрый слой сейчас недоступен, повтори через минуту."
        if mode in ("deep", "max"): txt = "GLM занят, отвечаю быстрым слоем. " + txt
''', '''        txt = _strip(self._fast_text(req))[0] or _safe("other")
        _ph = "deep_busy" if mode in ("deep", "max") else "fast_fallback"
''')
rep('{"model": TAG, "message": {"role": "assistant", "content": txt}, "done": False}, {"model": TAG',
    '{"model": TAG, "message": {"role": "assistant", "content": txt}, "done": False, "nox_phase": {"phase": _ph, "why": str(why)[:80]}}, {"model": TAG')
rep('ok = False; _acc = []\n', '''ok = False; _acc = []
        _int = _intent(_user_text); _guard = _SG(_int)
        def _emit(_p):
            if _p: _acc.append(_p); out({"model": TAG, "message": {"role": "assistant", "content": _p}, "done": False})
''')
rep('if t: _acc.append(t); out({"model": TAG, "message": {"role": "assistant", "content": t}, "done": False})',
    'if t:\n                        for _p in _guard.feed(t): _emit(_p)')
mm = re.search(r'            if not "".join\(_acc\)\.strip\(\):\n.*?\n.*?\n', s); assert mm, "no empty block"
s = s[:mm.start()] + '''            for _p in _guard.flush(): _emit(_p)
            if not "".join(_acc).strip():
                _t = _strip(self._fast_text(req), _int)[0] or _safe(_int)
                out({"model": TAG, "message": {"role": "assistant", "content": _t}, "done": False, "nox_phase": {"phase": "deep_busy" if _mode in ("deep", "max") else "empty_retry"}}); _acc.append(_t); ok = True
''' + s[mm.end():]
s = s.replace('j["status"] = "error"; j["text"] = str(e)', 'j["status"] = "error"; j["text"] = ""; j["phase"] = "deep_failed"')
rep('Не утверждай, что выполнил действие, если не выполнял."', 'Не утверждай, что выполнил действие, если не выполнял.\\n" + _NOXHF_LINE')
open(dst, "w", encoding="utf-8").write(s); print("patched NOXHF")
