echo "K1: rs_proc2"
export RUNNER_TRACKING_ID=""
cat > /tmp/rsproc.py <<'P'
import os,sys,time,signal,subprocess
pat=sys.argv[1]; log=sys.argv[2]
pids=[p for p in os.listdir('/proc') if p.isdigit()]
tgt=None
for p in pids:
    try:
        c=open(f'/proc/{p}/cmdline','rb').read().split(b'\0')
        if any(pat.encode() in x for x in c) and b'rsproc' not in b' '.join(c) and b'grep' not in c[0]:
            tgt=p;break
    except Exception: pass
if not tgt: print(pat,'not_found'); sys.exit(1)
cmd=[x.decode() for x in open(f'/proc/{tgt}/cmdline','rb').read().split(b'\0') if x]
env=dict(l.decode(errors='replace').split('=',1) for l in open(f'/proc/{tgt}/environ','rb').read().split(b'\0') if b'=' in l)
env.pop('RUNNER_TRACKING_ID',None)
cwd=os.readlink(f'/proc/{tgt}/cwd')
os.kill(int(tgt),signal.SIGTERM)
for i in range(40):
    if not os.path.exists(f'/proc/{tgt}'): break
    time.sleep(0.25)
else:
    os.kill(int(tgt),signal.SIGKILL); time.sleep(1)
subprocess.Popen(cmd,env=env,cwd=cwd,start_new_session=True,stdin=subprocess.DEVNULL,stdout=open(log,'ab'),stderr=subprocess.STDOUT)
print(pat,'restarted')
P
sup(){ supervisorctl status 2>/dev/null | awk '{print $1}' | while read p; do pp=$(supervisorctl pid $p 2>/dev/null); [ "$pp" = "$1" ] && echo $p; done | head -1; }
for pat in image_service.py web_server.py; do
  PID=$(pgrep -f "$pat" | head -1); S=$(sup "$PID")
  if [ -n "$S" ]; then supervisorctl restart $S >/dev/null 2>&1 && echo "$pat supervisor_restarted"
  else python3 /tmp/rsproc.py "$pat" /workspace/nox/logs/rs_$(echo $pat|cut -d. -f1).log; fi
done
sleep 20
echo "img_proc=$(pgrep -fc image_service.py) web_proc=$(pgrep -fc web_server.py)"
for u in /web/chat-v1d.html /api/nox/status /api/nox/memory/health; do echo "$u $(curl -s -o /dev/null -m 10 -w %{http_code} http://127.0.0.1:18091$u)"; done
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles; cb=$(date +%s)
bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
t0=$(date +%s.%N); C=$(curl -s -o /tmp/img.json -m 120 -w %{http_code} -H 'Content-Type: application/json' -d '{"prompt":"a cat in a spacesuit, cinematic","width":768,"height":768,"user_id":"qa-img"}' http://127.0.0.1:18091/img/generate); t1=$(date +%s.%N)
echo "img_generate code=$C sec=$(echo "$t1-$t0"|bc) has_url=$(grep -c -E 'url|file|path' /tmp/img.json)"
