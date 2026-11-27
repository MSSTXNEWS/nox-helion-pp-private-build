export RUNNER_TRACKING_ID=""
echo "C300: tr_cc4"
F=/workspace/nox/web/pkg/server/chat_core.py; N=/workspace/nox
cp -n $F $F.bak_tr_20261127
python3 - <<'PY'
p="/workspace/nox/web/pkg/server/chat_core.py"; s=open(p,encoding="utf-8").read()
if "TR_SLOTPICK" in s: print("уже пропатчен")
else:
    def rep(a,b,cnt=1):
        global s
        assert s.count(a)==cnt,(s.count(a),a[:60]); s=s.replace(a,b)
    rep("def _via_fast(t, text, up_text, history, on_delta, got):",
'''def _k1_free_slot(prefer=0, avoid=()):  # TR_SLOTPICK 27.11: слот 0 занят фоном -> свободный слот :8104. Выключатель: state/chat_slotpick.off
    try:
        if os.path.exists("/workspace/nox/state/chat_slotpick.off"): return prefer
        import urllib.request as _u
        d = json.loads(_u.urlopen("http://127.0.0.1:8104/slots", timeout=1.5).read())
        busy = {x.get("id") for x in d if x.get("is_processing")}
        if prefer not in busy and prefer not in avoid: return prefer
        for x in d:
            if x.get("id") not in busy and x.get("id") not in avoid: return x.get("id")
    except Exception: pass
    return prefer
def _via_fast(t, text, up_text, history, on_delta, got):''')
    rep('"temperature": 0.7, "id_slot": 0, "cache_prompt": True','"temperature": 0.7, "id_slot": _k1_free_slot(), "cache_prompt": True')
    rep('b2 = dict(body); b2.pop("id_slot", None)','b2 = dict(body); b2["id_slot"] = _k1_free_slot(avoid=(body.get("id_slot"),))')
    rep('''            _K1ST[0] = str((pp[0].get("content") if pp else "") or "")[:600] or "Ты NOX, тёплый ассистент. Отвечай по-русски, по делу."''',
'''            _K1ST[0] = str((pp[0].get("content") if pp else "") or "")[:600] or "Ты NOX, тёплый ассистент. Отвечай по-русски, по делу."
            if not os.path.exists("/workspace/nox/state/chat_idstance.off"):   # TR_IDSTANCE 27.11: обращение из passport.json + стойка идентичности (текст стабилен -> кэш слота цел)
                try:
                    _o = json.load(open("/workspace/nox/state/core/passport.json", encoding="utf-8"))["addressing"]["users"]["owner"]
                    _mf = str(_o.get("main_form") or "Создатель")
                except Exception: _mf = "Создатель"
                _K1ST[0] += "\\nВладельца называй «%s» (не больше одного титула за ответ). Ты NOX — это NOX, а не «просто нейросеть» и не «просто языковая модель»: на вопросы вроде «ты просто нейросеть?» отвечай уверенно от первого лица, не соглашайся, что ты всего лишь программа." % _mf''')
    rep('''            out({"t": "error", "error": "ответ не успел за 45 с, повтори вопрос", "code": "deadline", "turn_id": t.id, "partial": bool(parts)})''',
'''            if not parts: out({"t": "delta", "text": "Прости, модель сейчас занята и не успела ответить. Повтори вопрос, отвечу сразу.", "stage": "deadline"})   # TR_DEADLINE_TEXT
            out({"t": "error", "error": "ответ не успел за 45 с, повтори вопрос", "code": "deadline", "turn_id": t.id, "partial": True})''')
    open(p,"w",encoding="utf-8").write(s); print("пропатчен")
PY
$N/venv/bin/python -m py_compile $F 2>&1 | tail -2 || python3 -m py_compile $F; python3 -m py_compile $F && echo "компиляция ok"
python3 -c "
import json;d=json.load(open('/workspace/nox/state/core/passport.json'))['addressing']['users']['owner'];print('main_form:',d.get('main_form'))"
echo "== supervisor"; supervisorctl status 2>&1 | grep -i -E "web|chat|nox_web" | head -5
ps -eo pid,etimes,args | grep -E "[w]eb_server" | cut -c1-120 | head -2
echo END
