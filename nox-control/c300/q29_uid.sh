echo "K1: q29_uid"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
python3 - <<'PY'
import re,collections
l=open("/workspace/nox/state/s03_recall.log",errors="replace").read().splitlines()
c=collections.Counter(re.search(r"user_set=(\w+)",x).group(1) for x in l if "user_set=" in x); print("s03_recall user_set",dict(c),"lines",len(l))
PY
grep -nE "user_id|X-NOX-User|X-Nox-User" $N/web/pkg/server/web_server.py | cut -c1-190 | sed -E 's/(Bearer|token|password)[^"]{0,20}/\1.../' | head -25
grep -nE "X-NOX-User|X-Nox-User|header_up" /etc/caddy/Caddyfile 2>/dev/null | wc -l
echo END
