echo "K1: ln_p2"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; R=$N/web/pkg/webroot
c(){ curl -s -m ${3:-10} -o /tmp/ln_b -w "$1 %{http_code} %{time_total}s sz=%{size_download}\n" "127.0.0.1:$2$1"; }
bad=0; for f in $(cd $R; ls *.html); do o=$(curl -s -m 8 -o /dev/null -w "%{http_code}" 127.0.0.1:18091/web/$f); [ "$o" = 200 ] || { echo "web/$f $o"; bad=$((bad+1)); }; done; echo "18091 pages bad=$bad"
for p in $(grep -oE "handle(_path)? /[A-Za-z0-9_/.*-]+" $N/ops/web_chat_auth/Caddyfile | awk '{print $2}' | sed 's#/\*$##' | sort -u); do c $p 18091 6; done
for p in /api/nox/outbox /api/nox/agenda /api/nox/briefs /api/nox/self_now /api/nox/memory/health /api/chat/health /svc/_status /svc/nox-living/health /api/memory/recall; do c $p 18091 8; done
echo "== self_now"; curl -s -m8 127.0.0.1:18091/api/nox/self_now | python3 -c "
import sys,json
d=json.load(sys.stdin)
def walk(x,p=''):
    if isinstance(x,dict):
        for k,v in x.items():
            if any(s in k.lower() for s in ('sens','alive','count','total','mood','emo')): print(p+k, str(v)[:80])
            walk(v,p+k+'.')
walk(d)" 2>&1 | head -20
echo "== living health"; curl -s -m8 127.0.0.1:18091/svc/nox-living/health | head -c 300; echo
echo "== agenda keys"; curl -s -m8 127.0.0.1:18091/api/nox/agenda | head -c 250; echo
echo "== briefs"; curl -s -m8 127.0.0.1:18091/api/nox/briefs | head -c 250; echo
echo "== outbox"; curl -s -m8 127.0.0.1:18091/api/nox/outbox | head -c 200; echo
