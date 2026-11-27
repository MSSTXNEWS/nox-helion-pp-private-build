echo "K1: rs_recon2"
export RUNNER_TRACKING_ID=""
W=/workspace/nox
echo "--- running args"; tr '\0' ' ' </proc/$(ss -ltnp | grep ':8104 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)/cmdline | grep -oE -- "-t [0-9]+|-tb [0-9]+|--threads[^ ]* [0-9]+"
ls $W/agent/autotrain/ | grep -E "donor_hybrid|mode"; cat $W/agent/autotrain/mode
echo "--- owner_active.py"; wc -l $W/stewards/owner_active.py; cut -c1-200 $W/stewards/owner_active.py | head -70
echo "--- mem do_POST"; sed -n 120,215p $W/svc/mem/nox_mem.py | cut -c1-200
echo "--- Caddyfile"; cut -c1-160 $W/ops/web_chat_auth/Caddyfile | sed -n 1,80p
echo "--- client mem use"; grep -c "" /dev/null; curl -s -o /dev/null -w "%{http_code}\n" -X POST -H 'Content-Type: application/json' -d '{"q":"x","user":"u","k":1,"incognito":true}' http://127.0.0.1:18220/recall
echo "--- health"; curl -s http://127.0.0.1:18220/health | cut -c1-200
echo "--- train procs"; ps -eo pid,ni,args | grep -E "train_dpo|distill_v2|judge|rel_gates|autotrain" | grep -v grep | cut -c1-140
ls $W/state/*.off 2>/dev/null
