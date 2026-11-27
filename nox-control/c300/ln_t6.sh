echo "K1: ln_t6"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; now=$(date +%s)
age(){ [ -e "$1" ] && echo "$(( now-$(stat -c %Y $1) ))s" || echo none; }
echo "== supervisor non-running"; supervisorctl status | awk '$2!="RUNNING"{print $1,$2}'
echo "== disk/vram"; df -BG --output=avail,pcent /workspace | tail -1; nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader
echo "== disk_guard"; head -30 $N/ops/disk_guard.sh | cut -c1-150; echo age_log=$(age $N/agent/out/disk_guard.log); pgrep -af "disk_guard" | cut -c1-100; grep -rn "disk_guard" /etc/supervisor/conf.d $N/canon_night/selfheal_supervisor.sh $N/agent/nox_agents/selfheal.py 2>/dev/null | head -4 | cut -c1-160
echo "== training"; pgrep -af "char_cycle|autotrain|train_dpo|distill|ext_eval|p3_axis" | cut -c1-110 | head -8
for i in 1 2 3; do nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader | tr '\n' ' '; sleep 2; done; echo
ls -la --time-style=+%m-%d_%H:%M $N/state/p3 2>/dev/null | tail -12
echo "char_cycle log age=$(age $N/agent/out/char_cycle.log)"; tail -4 $N/agent/out/char_cycle.log | cut -c1-160
echo "owner_active: $(tail -2 $N/state/orch/owner_active.log | cut -c1-140)"
ls -t $N/state/p3/*ext_eval* $N/state/*/ext_eval* $N/ops/dpo/*ext_eval*.json 2>/dev/null | head -2
ls -t $N/state/*axis* $N/state/p3/*axis* $N/logs/*axis* 2>/dev/null | head -2
echo "== selfheal"; echo hb=$(age $N/state/agents/heartbeat/selfheal.json) log=$(age $N/state/agents/logs/selfheal.jsonl); tail -2 $N/state/agents/logs/selfheal.jsonl | cut -c1-240; pgrep -af selfheal | cut -c1-100 | head -3
echo "== backups"; crontab -l | grep -iE "backup|restic|soul" | cut -c1-140
find $N/backup $N/svc/restic -maxdepth 2 -mmin -90 -type f 2>/dev/null | head -5; ls -la --time-style=+%m-%d_%H:%M $N/backup | tail -8 | cut -c30-120
echo "== tunnel"; pgrep -af cloudflared | sed -E 's#https?://[^ ]*#URL#g' | cut -c1-120; supervisorctl status tunnel_manager nox_web_chat_tunnel | awk '{print $1,$2}'
tail -5 $N/agent/out/web_chat_tunnel_supervisord.log | sed -E 's#https?://[^ ]*#URL#g' | cut -c1-160
cat $N/ops/web_chat_auth/run_tunnel.sh | sed -E 's#https?://[^ ]*#URL#g;s/(token|TOKEN|pass)[=: ][^ ]*/\1=***/g' | head -25 | cut -c1-150
echo "== canon"; supervisorctl status nox_canon | awk '{print $1,$2,$3,$4,$5,$6}'; ls $N/canon | head -30 | tr '\n' ' '; echo
for f in genesis_chain stages autonomy_matrix; do ls -la --time-style=+%m-%d_%H:%M $(find $N/canon $N/state -maxdepth 3 -iname "*$f*" 2>/dev/null | head -2) 2>/dev/null | cut -c30-140; done
