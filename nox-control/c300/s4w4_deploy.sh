N=/workspace/nox; RAW="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF}/nox-control/c300/s4w4_files"; TS=$(date +%s); BK=$N/state/s4_backups; mkdir -p $BK
mask(){ sed -E 's#https://[a-z0-9-]+\.trycloudflare\.com#https://***.trycloudflare.com#g'; }
echo "S4W4 $(date +%F_%H:%M)"
for f in nox_uptime body_guard; do cp -a $N/mods/$f.py $BK/$f.py.$TS 2>/dev/null; curl -fsSL --retry 3 "$RAW/$f.py" -o $N/mods/$f.py || echo "FAIL $f"; done
for f in test_nox_uptime test_body_guard; do curl -fsSL --retry 3 "$RAW/$f.py" -o $N/mods/tests/$f.py || echo "FAIL $f"; done
cd $N/mods && python3 -I -m pytest -q tests/test_nox_uptime.py tests/test_body_guard.py 2>&1 | tail -1
echo "## patch weekly_exam p1 (chat_uptime_24h)"
W=$N/mods/weekly_exam.py; cp -a $W $BK/weekly_exam.py.$TS
python3 -I - <<'PY'
p="/workspace/nox/mods/weekly_exam.py"; s=open(p,encoding="utf-8").read()
if "chat_uptime_24h" in s: print("already patched")
else:
    key='    f = [free >= TH["disk_gb"], None if up is None else up >= TH["uptime_h"], None if oom is None else oom == TH["oom"]]\n'
    assert s.count(key)==1
    add='''    try:   # S4 28.11: аптайм чата за сутки от nox_uptime (цель >= 99.5%, канон гл.1)
        ud = jl(S + "/uptime_daily.json") or {}; cu = ud.get("chat_uptime_24h"); ns = ud.get("samples_24h") or 0
        v["chat_uptime_24h"] = cu; v["chat_uptime_samples"] = ns; f.append(None if cu is None or ns < 120 else cu >= 0.995)
    except Exception: pass
'''
    open(p,"w",encoding="utf-8").write(s.replace(key,key+add)); print("patched")
PY
python3 -I -m py_compile $W && echo "compile ok" || { echo "ОТКАТ weekly_exam"; cp -a $BK/weekly_exam.py.$TS $W; }
echo "## char_cycle.sh -> body_safe_restart"
C=$N/ops/dpo/char_cycle.sh; cp -a $C $BK/char_cycle.sh.$TS
python3 -I - <<'PY'
p="/workspace/nox/ops/dpo/char_cycle.sh"; s=open(p,encoding="utf-8").read()
a='bash $N/ops/body_restart.sh --force --cmd $HYB_CMD --reason "train_window: free VRAM for DPO"'
b='bash $N/ops/body_restart.sh --force --cmd $GPU_CMD --reason "train_window end: chat back to full GPU"'
if "body_safe_restart" in s: print("already patched")
else:
    assert s.count(a)==1 and s.count(b)==1
    s=s.replace(a,'bash $N/ops/body_safe_restart.sh --force --start ${HYB_CMD##*.cmd.} --reason "train_window: free VRAM for DPO"').replace(b,'bash $N/ops/body_safe_restart.sh --force --start ${GPU_CMD##*.cmd.} --reason "train_window end: chat back to full GPU"')
    open(p+".new","w",encoding="utf-8").write(s); import os; os.replace(p+".new",p); print("patched")
PY
bash -n $C && echo "bash -n ok" || { echo "ОТКАТ char_cycle"; cp -a $BK/char_cycle.sh.$TS $C; }
grep -c "body_safe_restart" $C
echo "## autotrain.sh start_donor: проверка VRAM до остановки донора"
A=$N/agent/autotrain/autotrain.sh; cp -a $A $BK/autotrain.sh.$TS
python3 -I - <<'PY'
p="/workspace/nox/agent/autotrain/autotrain.sh"; s=open(p,encoding="utf-8").read()
key='start_donor(){ # $1 = файл команды\n'
if "body_guard.py --fits" in s: print("already patched")
else:
    assert s.count(key)==1
    add=key+'  python3 -I /workspace/nox/mods/body_guard.py --fits "$1" >/dev/null 2>&1; [ $? -eq 1 ] && { log "$(basename $1): не помещается в свободную VRAM — донор не трогаю"; return 1; }   # S4 28.11: сторож тела\n'
    open(p+".new","w",encoding="utf-8").write(s.replace(key,add)); import os; os.replace(p+".new",p); print("patched")
PY
bash -n $A && echo "bash -n ok" || { echo "ОТКАТ autotrain"; cp -a $BK/autotrain.sh.$TS $A; }
echo "## svc_selfheal.py (K-OPS самолечение :8104)"
Y=$N/agent/nox_ops/svc_selfheal.py; cp -a $Y $BK/svc_selfheal.py.$TS
sed -i 's#C.N + "/ops/body_restart.sh", "--reason", "K-OPS#C.N + "/ops/body_safe_restart.sh", "--reason", "K-OPS#' $Y
python3 -I -m py_compile $Y && echo "compile ok $(grep -c body_safe_restart $Y)" || { echo "ОТКАТ svc_selfheal"; cp -a $BK/svc_selfheal.py.$TS $Y; }
echo "## supervisor nox_uptime"
D=/etc/supervisor/conf.d
if [ ! -f $D/nox_uptime.conf ]; then
cat > $D/nox_uptime.conf <<CONF
[program:nox_uptime]
command=python3 -I /workspace/nox/mods/nox_uptime.py
directory=/workspace/nox/mods
autostart=true
autorestart=true
startretries=10
startsecs=3
stopsignal=TERM
stopwaitsecs=10
redirect_stderr=true
stdout_logfile=/workspace/nox/logs/nox_uptime.log
stdout_logfile_maxbytes=2MB
stdout_logfile_backups=1
environment=NOX_ROOT="/workspace/nox"
CONF
fi
supervisorctl reread 2>&1 | tail -1; supervisorctl update 2>&1 | tail -1; supervisorctl restart nox_uptime 2>&1 | tail -1; sleep 8
S=$(supervisorctl status nox_uptime 2>&1 | awk '{print $2}'); echo "status=$S"
[ "$S" = "RUNNING" ] || { echo "ОТКАТ nox_uptime: убираю конфиг"; rm -f $D/nox_uptime.conf; supervisorctl reread >/dev/null 2>&1; supervisorctl update >/dev/null 2>&1; }
supervisorctl restart nox_weekly_exam 2>&1 | tail -1
sleep 80
echo "## uptime.log"; tail -n 4 $N/state/uptime.log | cut -c1-200
echo "## public_url.json"; python3 -I -c "
import json;d=json.load(open('$N/state/core/public_url.json'));print({k:(v if k not in ('url','prev') else (str(v)[:8]+'***' if v else v)) for k,v in d.items()})" 2>&1 | cut -c1-300
echo "## brief line"; python3 -I -c "
import json;d=json.load(open('$N/state/mind/morning_brief_v5.json'));print([x[:14] for x in d.get('lines',[]) if x.startswith('Адрес')], bool(d.get('public_url')))"
echo "## daily"; cat $N/state/core/uptime_daily.json | head -c 400; echo
echo "## exam p1 value"; python3 -I - <<'PY'
import sys; sys.path.insert(0,"/workspace/nox/mods")
import weekly_exam as W
v,f,why=W.p1(); print({k:v[k] for k in v if k in ("chat_uptime_24h","chat_uptime_samples","uptime_h")}, f)
PY
echo "## alerts"; tail -n 3 $N/state/alerts.jsonl 2>/dev/null | cut -c1-200
