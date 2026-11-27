echo "K1: ln_t7"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; now=$(date +%s)
age(){ [ -e "$1" ] && echo "$(( now-$(stat -c %Y $1) ))s" || echo none; }
echo "== soul hourly"; echo age=$(age $N/canon/soul_hourly_ok.json); head -c 400 $N/canon/soul_hourly_ok.json; echo; ls -la --time-style=+%m-%d_%H:%M $N/canon/soul | tail -5 | cut -c30-120
grep -n "soul_hourly\|restore\|verify" $N/canon/canon.py | head -12 | cut -c1-150
echo "== tunnel url"; U=$(cat $N/agent/out/WEB_CHAT_URL.txt 2>/dev/null); echo urlfile_age=$(age $N/agent/out/WEB_CHAT_URL.txt); curl -s -m12 -o /dev/null -w "tunnel_code=%{http_code}\n" "$U/" 
for f in $N/agent/out/web_chat_tunnel.log; do echo "log_age=$(age $f)"; grep -c "Registered tunnel connection" $f; done
ps -eo pid,etime,args | grep "[c]loudflared" | sed -E 's#https?://[^ ]*#URL#g' | cut -c1-140
echo "== DPO"; ps -o pid,etime,args -p 1968385 | cut -c1-110; tail -5 $N/ops/dpo/run7.log | cut -c1-150; cat $N/state/p3/train_verdict.json | cut -c1-360
echo "axis log age=$(age $N/state/p3/axis_rollback.jsonl)"; tail -2 $N/state/p3/axis_rollback.jsonl | cut -c1-200; ls -t $N/ops/dpo/*.log | head -3; ls -t $N/state/p3/ | head -4
grep -n "ext_eval" $N/ops/dpo/char_cycle.sh | head -3 | cut -c1-140; ls -la --time-style=+%m-%d_%H:%M $N/ops/dpo/ext_eval* $N/state/ext_eval* 2>/dev/null | cut -c30-140
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
