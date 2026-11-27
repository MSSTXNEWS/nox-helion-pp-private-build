echo "K1: ln_t8"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; now=$(date +%s)
age(){ [ -e "$1" ] && echo "$(( now-$(stat -c %Y $1) ))s" || echo none; }
echo "soul_hourly_ok age=$(age $N/canon/soul_hourly_ok.json)"; python3 -c "
import json;d=json.load(open('$N/canon/soul_hourly_ok.json'));print({k:d[k] for k in d if k!='ts'}, d['ts'])"
ls -lt --time-style=+%m-%d_%H:%M $N/canon/soul | head -4 | cut -c30-120
echo "canon daemon logs: out_age=$(age $N/canon/daemon.out) err_age=$(age $N/canon/daemon.err)"; tail -3 $N/canon/daemon.out | cut -c1-200; tail -3 $N/canon/daemon.err | cut -c1-200
grep -n "hourly\|3600\|def daemon" $N/canon/canon.py | head -10 | cut -c1-160
echo "== owner gate tunnel"
G=$N/state/owner_gate; ls -la --time-style=+%m-%d_%H:%M $G | cut -c30-100
U=$(grep -ohE 'https://[a-z0-9-]+\.trycloudflare\.com' $G/cf.log | tail -1); echo "url_found=$([ -n "$U" ] && echo yes || echo no)"
[ -n "$U" ] && curl -s -m15 -o /dev/null -w "gate_tunnel_code=%{http_code}\n" "$U/"
tail -3 $G/cf.log | sed -E 's#https?://[^ ]*#URL#g' | cut -c1-160
pgrep -af "owner_gate|state/owner_gate" | cut -c1-120
ps -eo pid,etime,args | grep "[m]etrics 127.0.0.1:20999" | cut -c1-60; cat $G/Caddyfile | sed -E 's#https?://[^ ]*#URL#g' | head -12
