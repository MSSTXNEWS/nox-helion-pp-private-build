echo "K1: rs_recon"
export RUNNER_TRACKING_ID=""
W=/workspace/nox
echo "--- cmd"; cat $W/agent/autotrain/donor_hybrid.cmd | sed -E 's/(--api-key|--key)[ =][^ ]+/\1 ***/g'
echo "--- body_restart"; sed -n 1,40p $W/ops/body_restart.sh | cut -c1-200
echo "--- owner_active"; grep -rIl owner_active $W/ops $W/agent 2>/dev/null | head -20
echo "--- char_cycle"; wc -l $W/ops/dpo/char_cycle.sh; sed -n 1,80p $W/ops/dpo/char_cycle.sh | cut -c1-220
echo "--- mem routes"; grep -nE "route|POST|path ==|startswith\(\"/" $W/svc/mem/nox_mem.py | head -40
echo "--- caddy"; grep -n -B2 -A6 "memory/health" $W/ops/web_chat_auth/Caddyfile
echo "--- nice"; ps -eo pid,ni,cls,args --sort=-pcpu | head -12 | cut -c1-160
echo "--- load"; cat /proc/loadavg; nproc
