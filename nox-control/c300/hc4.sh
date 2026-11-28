echo "K1: hc4"
# Канон: чат первый. Тело :8104 не помещается рядом с тренером (свободно ~12 ГБ). Останавливаю текущий DPO-круг (данные не удаляются), char_cycle вернёт тело на GPU.
export RUNNER_TRACKING_ID=""
T=$(pgrep -f train_dpo.py | head -1); [ -n "$T" ] && kill -TERM $T && echo "train_term=$T"
sleep 20; pgrep -f train_dpo.py >/dev/null && { kill -9 $(pgrep -f train_dpo.py); echo train_kill9; }
sleep 10; echo "vram=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)"
echo "br_running=$(pgrep -fc body_restart.sh)"
if [ "$(pgrep -fc body_restart.sh)" = "0" ] && ! ss -ltn | grep -q ':8104 '; then
  setsid nohup bash /workspace/nox/ops/body_restart.sh --force --cmd /workspace/nox/agent/autotrain/donor_hybrid.cmd.gpu_ncmoe0 >/tmp/br_hc4.log 2>&1 < /dev/null & echo br_started
fi
for i in $(seq 1 30); do sleep 10; c=$(curl -s -o /dev/null -m 3 -w %{http_code} http://127.0.0.1:8104/health); [ "$c" = 200 ] && { echo "h8104=200 after=$((i*10))s"; break; }; done
echo "final_h8104=$(curl -s -o /dev/null -m 3 -w %{http_code} http://127.0.0.1:8104/health) br=$(pgrep -fc body_restart.sh)"
echo END
