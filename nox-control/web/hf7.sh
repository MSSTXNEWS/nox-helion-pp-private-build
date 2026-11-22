#!/bin/bash
# final: настоящая Совесть (StreamGuard) + действия с подтверждением в веб-пути, душа merged (deep/fallback), строка про приветствие. :8082/:8081 не трогаем.
cd /root/nox; TS=$(date +%Y%m%d%H%M%S); W=/root/nox/web_server.py; Q=/root/nox/repo/nox-control; SOUL=$Q/qs6/soul_prompt_ru.txt
PS=/root/nox/src/wow7/prime/soul_prime_v3.txt; P1=$Q/wow7/PRIME/soul_prime_v3.txt; P2=$Q/wow7/prime/soul_prime_v3.txt
cat > /tmp/hf2_patch_web.py <<'PYEOF'
"""Хотфикс 2: настоящая Совесть (StreamGuard) поверх самописной + удаление прошлых запросов с превью/подтверждением в чат-пути.
usage: hf2_patch_web.py SRC DST"""
import re, sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()
if "NOXHF2" in s:
    open(dst, "w", encoding="utf-8").write(s); print("already NOXHF2"); sys.exit(0)
assert "NOXHF" in s, "need NOXHF base"
blk = r'''# NOXHF2: настоящая Совесть + действия с подтверждением
import sqlite3 as _sq3, secrets as _sec
try:
    sys.path.insert(0, "/root/nox/src/wow7/brain")
    import conscience as _csc
    _CONS = _csc.Conscience("enforce")
    class _Both:
        """StreamGuard пакета, затем самописный фильтр (защита в глубину)."""
        def __init__(self, intent, text):
            self.a = _csc.StreamGuard(_CONS, {"block": "", "user_text": text, "intent": intent, "asked_status": intent == "telemetry_q", "prev": []}); self.b = _SG(intent)
        def feed(self, p):
            o = []
            for x in self.a.feed(p): o += self.b.feed(x)
            return o
        def flush(self):
            o = []
            for x in self.a.flush(): o += self.b.feed(x)
            return o + self.b.flush()
    def _mkguard(intent, text):
        try: return _Both(intent, text)
        except Exception as _ge:
            print('NOXHF2 guard fallback:', _ge, flush=True); return _SG(intent)
    print("NOXHF2 conscience: on", flush=True)
except Exception as _e:
    print("NOXHF2 conscience: fallback (%s)" % _e, flush=True)
    def _mkguard(intent, text): return _SG(intent)
_DEL_RE = _hre.compile(r"(удал|сотр|очист|забудь|убери)\w*.*(запрос|сообщен|реплик|истори|переписк)", _hre.I)
_YES_RE = _hre.compile(r"^\s*(да|подтвержда\w*|удаляй|удали|ок|окей|давай)[\s!.)]*$", _hre.I)
_NO_RE = _hre.compile(r"^\s*(нет|отмена|не надо|стоп|не удаляй)[\s!.)]*$", _hre.I)
_UNDO_RE = _hre.compile(r"верни\w*\s+(удал|запрос)|отмени\w*\s+удален|undo", _hre.I)
_PEND = {}; _DELLOG = {"until": 0, "turns": [], "eps": [], "rid": None}
_TURNS = "/root/nox/logs/chat_turns.jsonl"; _DB = "/root/nox/memory/s03.db"
def _act_frames(h, text, meta=None):
    h.send_response(200); h.send_header("Content-Type", "application/x-ndjson"); h.send_header("Cache-Control", "no-cache"); h.send_header("Connection", "close"); h.end_headers()
    f1 = {"model": TAG, "message": {"role": "assistant", "content": text}, "done": False}
    if meta: f1["nox_meta"] = meta
    for o in (f1, {"model": TAG, "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"}):
        h.wfile.write((json.dumps(o, ensure_ascii=False) + "\n").encode())
    h.wfile.flush(); h.close_connection = True
def _del_count(text, total):
    t = text.lower()
    if _hre.search(r"\bвс[её]\b", t): return total
    m = _hre.search(r"\b(\d+)\b", t)
    if m: return max(1, int(m.group(1)))
    return total if _hre.search(r"прошл\w*\s+запрос\w*|запросы|запросов|сообщения", t) else 1
def _noxhf_action(h, req, text):
    now = time.time(); t = (text or "").strip()
    if not t or len(t) > 160: return False
    users = [m.get("content") for m in (req.get("messages") or [])[:-1] if m.get("role") == "user" and isinstance(m.get("content"), str) and m.get("content").strip()]
    p = _PEND.get("del")
    if p and now > p["until"]: _PEND.pop("del", None); p = None
    if p and _NO_RE.match(t):
        _PEND.pop("del", None); _act_frames(h, "Хорошо, ничего не удаляю."); return True
    if p and _YES_RE.match(t):
        _PEND.pop("del", None); sel = set(p["texts"]); rid = "del-" + _sec.token_hex(3); kept, gone = [], []
        try:
            for l in open(_TURNS, encoding="utf-8").read().split("\n"):
                if not l.strip(): continue
                try: o = json.loads(l)
                except Exception: kept.append(l); continue
                (gone if o.get("user") in sel else kept).append(l)
            open(_TURNS + ".bak_hotfix2_del", "a", encoding="utf-8").write("\n".join(gone) + ("\n" if gone else ""))
            open(_TURNS + ".tmp", "w", encoding="utf-8").write("\n".join(kept) + "\n"); os.replace(_TURNS + ".tmp", _TURNS)
        except Exception as e: gone = []; print("NOXHF2 del turns:", e, flush=True)
        eps = []
        try:
            c = _sq3.connect(_DB, timeout=10)
            for tx in sel:
                for (i,) in c.execute("select id from mem_episodes where role='user' and status='active' and text=?", (tx,)).fetchall():
                    c.execute("update mem_episodes set status='revoked' where id=?", (i,)); eps.append(i)
            c.commit(); left = sum(c.execute("select count(*) from mem_episodes where status='active' and role='user' and text=?", (tx,)).fetchone()[0] for tx in sel); c.close()
        except Exception as e: left = -1; print("NOX HF2 del mem:", e, flush=True)
        left_t = sum(1 for l in open(_TURNS, encoding="utf-8") if '"user"' in l and any(json.dumps(x, ensure_ascii=False)[1:-1] in l for x in sel))
        _DELLOG.update(until=now + 600, turns=gone, eps=eps, rid=rid)
        ok = left_t == 0 and left == 0
        msg = ("Удалил %d запрос(а) из журнала ходов и отозвал %d записей памяти, проверил чтением: %s. Квитанция %s; вернуть можно в течение 10 минут командой «верни удалённое». На экране эта вкладка сохранит старые реплики до обновления." % (len(sel), len(eps), "следов нет" if ok else "ЧАСТЬ ОСТАЛАСЬ", rid))
        _act_frames(h, msg, {"receipt": {"receipt_id": rid, "kind": "delete_history", "removed_turns": len(gone), "revoked_memory": len(eps), "verified_absent": ok}}); return True
    if _UNDO_RE.search(t):
        if now > _DELLOG["until"] or not (_DELLOG["turns"] or _DELLOG["eps"]): _act_frames(h, "Возвращать нечего: недавних удалений нет."); return True
        try:
            open(_TURNS, "a", encoding="utf-8").write("\n".join(_DELLOG["turns"]) + "\n")
            c = _sq3.connect(_DB, timeout=10)
            for i in _DELLOG["eps"]: c.execute("update mem_episodes set status='active' where id=?", (i,))
            c.commit(); c.close()
        except Exception as e: _act_frames(h, "Мессир, вернуть не удалось: %s." % str(e)[:80]); return True
        n = len(_DELLOG["turns"]); _DELLOG.update(until=0, turns=[], eps=[]); _act_frames(h, "Вернул %d запрос(а) с ответами (квитанция %s)." % (n, _DELLOG["rid"])); return True
    if _DEL_RE.search(t) and not p:
        if not users: _act_frames(h, "Удалять нечего: прошлых запросов в этом диалоге нет."); return True
        n = min(_del_count(t, len(users)), len(users)); sel = users[-n:]
        _PEND["del"] = {"texts": sel, "until": now + 120}
        lines = ["%d. «%s»" % (i, x[:48].replace("\n", " ")) for i, x in enumerate(sel, 1)]
        _act_frames(h, "Удалить %d прошлых запрос(а) вместе с моими ответами на них?\n%s\nКопию держу 10 минут: вернуть можно командой «верни удалённое». Подтверждаешь — «да» или «нет»?" % (n, "\n".join(lines)))
        return True
    return False
'''
m = re.search(r"^_MSK = .*$", s, re.M); assert m
s = s[:m.start()] + blk + s[m.start():]
assert "_guard = _SG(_int)" in s
s = s.replace("_guard = _SG(_int)", "_guard = _mkguard(_int, _user_text)", 1)
a = '        _mode = _md or "auto"; jid = None\n'
assert a in s
s = s.replace(a, '        try:\n            if _noxhf_action(self, req, _user_text): return\n        except (BrokenPipeError, ConnectionResetError): return\n        except Exception as _ae: print("NOXHF2 action error:", _ae, flush=True)\n' + a, 1)
s = s.replace('_NOXHF_LINE = ("Никогда', '_NOXHF_LINE = ("На приветствие не называй модель, систему и дату: 1–3 живые фразы. Никогда', 1)
open(dst, "w", encoding="utf-8").write(s); print("patched NOXHF2")

PYEOF
[ -f $PS ] || { echo "no prime soul"; exit 1; }
for F in $W $SOUL $P1 $P2; do [ -f $F ] && { ls $F.bak_final_* >/dev/null 2>&1 || cp -a $F $F.bak_final_$TS; }; done
cat > /root/nox/final_rollback.sh <<R
#!/bin/bash
for F in $W $SOUL $P1 $P2; do b=\$(ls \$F.bak_final_* 2>/dev/null | head -1); [ -n "\$b" ] && cp -a \$b \$F; done
rm -f /root/nox/.soul_merged_final
python3 /root/nox/hf_restart.py 8091 /root/nox/logs/web_server.log; sleep 4
curl -s -m5 -o /dev/null -w "web %{http_code}\n" http://127.0.0.1:8091/web/chat.html
R
chmod +x /root/nox/final_rollback.sh
python3 - <<P || exit 1
import os
soul="$SOUL"; ps="$PS"; flag="/root/nox/.soul_merged_final"
RULE="На приветствие не называй модель, систему и дату: 1–3 живые фразы."
if not os.path.exists(flag):
    cur=open(soul,encoding="utf-8").read(); prime=open(ps,encoding="utf-8").read().strip()
    i=cur.find("[LIVING_NOX_V1"); assert i>=0, "no LIVING block"
    living=cur[i:].strip(); old=cur[:i].strip()
    body,sep,main=prime.partition("## Главное"); assert sep, "no Главное in prime"
    rules="Правила ответа:\n- Никогда не пересказывай блок внутреннего состояния и телеметрию, если Создатель прямо не спросил о состоянии/сервере. На приветствие — 1–3 живые фразы. Не предлагай списков «Что хочешь: →…».\n- "+RULE
    new=body.strip()+"\n\n## Из прежней редакции души (сохранено)\n"+old+"\n\n"+living+"\n\n"+rules+"\n\n## Главное"+main
    open(soul,"w",encoding="utf-8").write(new+"\n"); open(flag,"w").write("1"); print("soul merged chars", len(new), "living kept", "LIVING_NOX_V1" in new)
else: print("soul already merged")
for f in ("$P1","$P2"):
    if os.path.exists(f):
        t=open(f,encoding="utf-8").read()
        if RULE not in t:
            a,s,m=t.partition("## Главное")
            t=(a.rstrip()+"\n\n- "+RULE+"\n\n"+s+m) if s else (t.rstrip()+"\n\n- "+RULE+"\n")
            open(f,"w",encoding="utf-8").write(t); print("prime rule added", os.path.basename(os.path.dirname(f)))
P
python3 /tmp/hf2_patch_web.py $W /tmp/ws2.py || exit 1
python3 -I -m py_compile /tmp/ws2.py || { echo compile fail; bash /root/nox/final_rollback.sh; exit 1; }
cp /tmp/ws2.py $W
ask(){ curl -sN -m150 http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d "$1" | python3 -c "
import sys,json
t=''
for l in sys.stdin:
    try: o=json.loads(l)
    except Exception: continue
    t+=(o.get('message') or {}).get('content','')
    if o.get('error'): t+='[ERR '+str(o['error'])[:80]+']'
print(repr(t[:$2]))"; }
mk(){ python3 -c "import json,sys; print(json.dumps({'messages':json.loads(sys.argv[1]),'stream':True},ensure_ascii=False))" "$1"; }
echo "== restart web"; python3 /root/nox/hf_restart.py 8091 /root/nox/logs/web_server.log; sleep 6
code=$(curl -s -m8 -o /dev/null -w "%{http_code}" http://127.0.0.1:8091/web/chat.html); echo "web: $code"; grep -h "NOXHF2" /root/nox/logs/web_server.log | tail -2
if [ "$code" != "200" ]; then echo ROLLBACK; bash /root/nox/final_rollback.sh; exit 1; fi
bad=0
for i in 1 2 3; do r=$(ask "$(mk '[{"role":"user","content":"привет"}]')" 200); echo "привет#$i -> $r"; { [ "$r" = "''" ] || echo "$r" | grep -q ERR; } && bad=1; done
[ $bad = 1 ] && { echo ROLLBACK; bash /root/nox/final_rollback.sh; exit 1; }
echo "как сервер? -> $(ask "$(mk '[{"role":"user","content":"как сервер?"}]')" 200)"
T="хотфикс проверка 77 расскажи коротко про луну"
echo "ход: len $(ask "$(mk "[{\"role\":\"user\",\"content\":\"$T\"}]")" 4000 | wc -c)"
echo "превью -> $(ask "$(mk "[{\"role\":\"user\",\"content\":\"$T\"},{\"role\":\"assistant\",\"content\":\"ок\"},{\"role\":\"user\",\"content\":\"удали прошлые запросы\"}]")" 400)"
echo "подтверждение -> $(ask "$(mk "[{\"role\":\"user\",\"content\":\"$T\"},{\"role\":\"assistant\",\"content\":\"ок\"},{\"role\":\"user\",\"content\":\"удали прошлые запросы\"},{\"role\":\"assistant\",\"content\":\"?\"},{\"role\":\"user\",\"content\":\"да\"}]")" 500)"
echo "== pages"; for p in chat resonance templates system training; do echo -n "$p:$(curl -s -m6 -o /dev/null -w %{http_code} http://127.0.0.1:8091/web/$p.html) "; done; echo
echo "rollback: bash /root/nox/final_rollback.sh"
