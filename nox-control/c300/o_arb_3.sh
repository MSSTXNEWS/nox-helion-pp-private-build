set -u
NOX=/workspace/nox; TS=$(date +%Y%m%d_%H%M%S)
cp $NOX/agent/arbiter.py $NOX/agent/arbiter.py.bak_o_$TS
cat > $NOX/agent/arbiter.py.new <<'PYEOF'
#!/usr/bin/env python3
"""NOX arbiter: чат/задачи в приоритете, обучение уступает. stdlib only. Только STOP/CONT/renice, ничего не убивает."""
import os, sys, time, json, signal, subprocess, urllib.request, re
W = '/workspace/nox'
STATE = W + '/state/arbiter.json'
LOG = W + '/arbiter.log'
PID = W + '/state/arbiter.pid'
BASE = 'http://127.0.0.1:8091'
SWAP = 'http://127.0.0.1:8200'
TICK = 2
IDLE_RESUME = 60        # с тишины до SIGCONT
MAX_PAUSE = 1800        # макс. пауза подряд
GPU_TARGET = 90
PATS = [r'distill_v2\.py\s+train', r'/workspace/nox/ops/v5_[^ ]*\.py']
EXCL = [r'ckpt_guard', r'arbiter\.py', r'llama-swap', r'llama-server', r'web_server\.py']
CKPT_DIRS = [W + '/distill_v2/ckpt']

def log(msg):
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 1000000:
            os.replace(LOG, LOG + '.1')
        with open(LOG, 'a') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + msg + '\n')
    except Exception:
        pass

def get(url, t=1.5, data=None):
    try:
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'} if data else {})
        with urllib.request.urlopen(req, timeout=t) as r:
            return r.status, r.read(200000).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, ''
    except Exception:
        return 0, ''

def jget(url):
    s, b = get(url)
    if s != 200: return None
    try: return json.loads(b)
    except Exception: return None

BUSY_KEYS = re.compile(r'(active|inflight|in_flight|busy|streaming|generating|pending|queue|turns?_active|running_turns)', re.I)
def walk(o, path=''):
    """ищет признаки занятости: булевы/числа в ключах active/busy/inflight..."""
    hits = []
    if isinstance(o, dict):
        for k, v in o.items():
            p = path + '.' + str(k)
            if BUSY_KEYS.search(str(k)):
                if (isinstance(v, bool) and v) or (isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0) or (isinstance(v, (list, dict)) and len(v) > 0):
                    hits.append(p)
            hits += walk(v, p)
    elif isinstance(o, list):
        for i, v in enumerate(o[:20]): hits += walk(v, path + '[]')
    return hits

def chat_active():
    try:  # chat_guard: свежий state/orch/chat_hold = ход Мессира
        if time.time() - os.path.getmtime(W + '/state/orch/chat_hold') < 4: return 'chat:chat_hold'
    except Exception: pass
    for u in (BASE + '/api/nox/status', 'http://127.0.0.1:8090/health'):
        j = jget(u)
        if isinstance(j, dict):
            h = j.get('health', j)
            try:
                if int(h.get('running') or 0) > 0: return 'chat:core.running=%s' % h.get('running')
                if int((h.get('glm') or {}).get('inflight') or 0) > 0: return 'chat:glm.inflight'
            except Exception: pass
            break
    return None

def tasks_active():
    for u in ('/svc/agents/', '/svc/advisors/'):
        j = jget(BASE + u)
        if j is not None:
            h = walk(j)
            if h: return 'tasks:%s%s' % (u, h[0])
    return None

def swap_active():
    j = jget(SWAP + '/running')
    if not j: return None
    lst = j.get('running') if isinstance(j, dict) else j
    for m in (lst or []):
        st = str(m.get('state', '')).lower() if isinstance(m, dict) else ''
        if st in ('starting', 'loading', 'inflight', 'busy', 'streaming'):
            return 'llama:' + st
    return None

def gpu():
    try:
        o = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=4).stdout.split(',')
        return int(o[0]), int(o[1]), int(o[2])
    except Exception:
        return -1, -1, -1

def procs():
    out = {}
    me = os.getpid()
    ppid = {}
    cmd = {}
    for d in os.listdir('/proc'):
        if not d.isdigit(): continue
        try:
            c = open('/proc/%s/cmdline' % d, 'rb').read().replace(b'\0', b' ').decode('utf-8', 'replace').strip()
            st = open('/proc/%s/stat' % d).read()
            pp = int(st.rsplit(')', 1)[1].split()[1])
            ppid[int(d)] = pp; cmd[int(d)] = c
        except Exception:
            continue
    sel = set()
    for p, c in cmd.items():
        if p == me or not c: continue
        if any(re.search(x, c) for x in EXCL): continue
        if any(re.search(x, c) for x in PATS):
            if re.match(r'^(\S*python3?)\b', c):
                sel.add(p)
    changed = True
    while changed:
        changed = False
        for p, pp in ppid.items():
            if pp in sel and p not in sel and p != me and not any(re.search(x, cmd.get(p, '')) for x in EXCL):
                sel.add(p); changed = True
    return {p: cmd[p][:120] for p in sel}

def pstate(p):
    try: return open('/proc/%d/stat' % p).read().rsplit(')', 1)[1].split()[0]
    except Exception: return None

def ckpt_writing():
    """идёт запись ckpt: недавно изменённый файл .pt/.safetensors/.ckpt/.tmp или открытый на запись"""
    now = time.time()
    for d in CKPT_DIRS:
        for root, ds, fs in os.walk(d):
            if root.count('/') - d.count('/') > 3: ds[:] = []
            for f in fs:
                if f.endswith(('.pt', '.pth', '.safetensors', '.ckpt', '.tmp', '.part', '.bin')):
                    try:
                        if now - os.path.getmtime(os.path.join(root, f)) < 6 and os.path.getsize(os.path.join(root, f)) > 1000000:
                            return True
                    except Exception: pass
    return False

def sig(pids, s):
    for p in pids:
        try: os.kill(p, s)
        except Exception: pass

def nice(pids, n, io):
    for p in pids:
        try: os.setpriority(os.PRIO_PROCESS, p, n)
        except Exception: pass
        subprocess.run(['ionice', '-c', '3' if io else '2', '-n', '0' if not io else '7', '-p', str(p)] if io else ['ionice', '-c', '2', '-n', '4', '-p', str(p)], capture_output=True)

def owner():
    try: return json.load(open(STATE)).get('owner', {})
    except Exception: return {}

def save(st):
    st['owner'] = owner()
    tmp = STATE + '.tmp'
    json.dump(st, open(tmp, 'w'), ensure_ascii=False)
    os.replace(tmp, STATE)
    try:
        d = W + '/web/site/data/arbiter.json'
        json.dump(st, open(d + '.tmp', 'w'), ensure_ascii=False); os.replace(d + '.tmp', d)
    except Exception: pass

def main():
    if os.path.exists(PID):
        try:
            old = int(open(PID).read())
            if os.path.exists('/proc/%d' % old) and 'arbiter' in open('/proc/%d/cmdline' % old).read():
                print('already running', old); return
        except Exception: pass
    open(PID, 'w').write(str(os.getpid()))
    log('start pid=%d' % os.getpid())
    mode, since, last_act, paused_at = 'train', time.time(), 0.0, None
    reason = 'старт'; nice_act = nice_cap = False
    def on_term(*a):
        sig(list(procs()), signal.SIGCONT); log('stop: SIGCONT всем'); sys.exit(0)
    signal.signal(signal.SIGTERM, on_term)
    while True:
        try:
            now = time.time()
            ps = procs(); pids = list(ps)
            ch = chat_active(); tk = tasks_active(); sw = swap_active()
            util, mu, mt = gpu()
            stopped = [p for p in pids if pstate(p) == 'T']
            # чужая GPU-нагрузка при остановленном обучении = активность
            ext = 'gpu-ext:%d%%' % util if (pids and len(stopped) == len(pids) and util >= 40) else None
            act = ch or tk or sw or ext
            ow = owner()
            if ow.get('force_pause'): act = act or 'owner:force_pause'
            if act:
                last_act = now
                newmode = 'chat' if ch else 'tasks'
                if ow.get('no_stop'):
                    if not nice_act:
                        nice(pids, 19, True); nice_act = True; log('RENICE19 (owner no_stop) %s pids=%d util=%d' % (act, len(pids), util))
                    reason = act + ' (renice)'
                    if mode != newmode: mode, since = newmode, now
                elif len(stopped) < len(pids):
                    if ckpt_writing():
                        reason = 'жду конец записи ckpt'
                    else:
                        sig(pids, signal.SIGSTOP); paused_at = paused_at or now
                        log('PAUSE %s pids=%d util=%d' % (act, len(pids), util)); reason = act
                        mode, since = newmode, now
                else:
                    if mode != newmode: mode, since = newmode, now
                if stopped and paused_at is None: paused_at = now
                if paused_at and now - paused_at > MAX_PAUSE:
                    sig(pids, signal.SIGCONT); nice(pids, 19, True); nice_act = True; paused_at = None
                    log('MAXPAUSE 30min -> CONT + renice 19 (%s)' % act); reason = 'лимит паузы 30 мин'; mode, since = 'train', now
            else:
                quiet = now - last_act
                if stopped and quiet >= IDLE_RESUME:
                    sig(pids, signal.SIGCONT); nice(pids, 0, False); paused_at = None; nice_act = nice_cap = False
                    log('RESUME quiet=%ds pids=%d' % (quiet, len(pids))); mode, since, reason = 'train', now, 'тишина %ds' % quiet
                elif not stopped:
                    if nice_act and quiet >= IDLE_RESUME:
                        nice(pids, 0, False); nice_act = False
                        log('RESUME nice0 quiet=%ds pids=%d' % (quiet, len(pids))); mode, since, reason = 'train', now, 'тишина %ds' % quiet
                    cap = int(ow.get('gpu_cap', GPU_TARGET))
                    if util > cap and pids and not nice_cap:
                        nice(pids, 19, True); nice_cap = True; log('renice 19 util=%d>%d' % (util, cap)); reason = 'util>%d' % cap
                    elif util <= cap - 15 and nice_cap and not nice_act:
                        nice(pids, 0, False); nice_cap = False; log('renice 0 util=%d' % util)
                    if mode != 'train' and not nice_act: mode, since = 'train', now
            save({'mode': mode, 'since': int(since), 'util': util, 'mem_mb': mu, 'mem_total_mb': mt,
                  'reason': reason, 'paused': len(stopped) > 0, 'nprocs': len(ps), 'procs': dict(list(ps.items())[:6]), 'ts': int(now), 'pid': os.getpid(),
                  'signals': {'chat': ch, 'tasks': tk, 'llama': sw, 'ext': ext}})
        except SystemExit:
            raise
        except Exception as e:
            log('ERR %r' % (e,))
        t0 = time.time()
        while time.time() - t0 < TICK:   # быстрый путь: свежий chat_hold прерывает ожидание
            time.sleep(0.4)
            try:
                if time.time() - os.path.getmtime(W + '/state/orch/chat_hold') < 1.5 and mode != 'chat': break
            except Exception: pass

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'status':
        print(open(STATE).read()); sys.exit(0)
    main()
PYEOF
python3 -I -m py_compile $NOX/agent/arbiter.py.new && mv $NOX/agent/arbiter.py.new $NOX/agent/arbiter.py && echo "compile ok"
OLD=$(cat $NOX/state/arbiter.pid); kill -TERM $OLD 2>/dev/null; sleep 3   # свой демон: SIGTERM -> SIGCONT и выход
nohup setsid /workspace/nox/venv/bin/python $NOX/agent/arbiter.py >/dev/null 2>&1 </dev/null &
sleep 5; echo "arbiter pids: $(pgrep -f 'agent/arbiter.py' | tr '\n' ' ') (old $OLD)"
mkdir -p $NOX/web/site/data
python3 - <<'P'
import json,shutil,time,os
f='/workspace/nox/web/site/qa/registry.json'
r=json.load(open(f)); c=r['commands']
if 'arbiter.status' in c: print('REG already'); raise SystemExit
shutil.copy(f,f+'.bak_o_'+time.strftime('%Y%m%d_%H%M%S'))
c['arbiter.status']={"desc":"Арбитр ресурсов: режим chat|tasks|train, GPU, пауза обучения (только чтение)","method":"GET","endpoint":"/data/arbiter.json","params":{"type":"object","properties":{}},"confirm":False}
json.dump(r,open(f+'.tmp','w'),ensure_ascii=False,indent=1); os.replace(f+'.tmp',f); print('REG added; commands now',len(c))
P
curl -s -m4 -w ' [%{http_code}]\n' 127.0.0.1:8091/data/arbiter.json | head -c 300
echo "== TEST"; echo "owner: $(python3 -c "import json;print(json.load(open('$NOX/state/arbiter.json')).get('owner'))")"
echo "T0 $(date +%T.%N)"
curl -s -m 90 -o /tmp/o_chat.out -w 'chat http %{http_code} %{time_total}s\n' -H 'Content-Type: application/json' -d '{"model":"nox-helion:latest","stream":false,"nox_mode":"fast","conversation_id":"o-arbiter-test","messages":[{"role":"user","content":"привет"}]}' 127.0.0.1:8091/api/chat &
for i in 1 2 3 4 5 6; do sleep 0.5; echo "$(date +%T.%N | cut -c1-12) $(python3 -c "import json;d=json.load(open('$NOX/state/arbiter.json'));print(d['mode'],d['paused'],d['reason'])")"; done
wait; head -c 200 /tmp/o_chat.out; echo
for p in $(pgrep -f "distill_v2.py train"); do echo "train $p state=$(awk '{print $3}' /proc/$p/stat) nice=$(awk '{print $19}' /proc/$p/stat)"; done
tail -6 $NOX/arbiter.log | cut -c1-200
echo "-- ждём 75 с"; sleep 75
for p in $(pgrep -f "distill_v2.py train"); do echo "train $p state=$(awk '{print $3}' /proc/$p/stat) nice=$(awk '{print $19}' /proc/$p/stat)"; done
tail -6 $NOX/arbiter.log | cut -c1-200; head -c 400 $NOX/state/arbiter.json; echo
