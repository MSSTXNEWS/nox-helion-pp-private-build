echo "K1: tp1"
# Создатель 28.11 20:27 МСК: «обучение на паузу». Останавливаю круг (данные целы), окно обучения закрыто флагом.
export RUNNER_TRACKING_ID=""; N=/workspace/nox
touch $N/state/train_window.off $N/state/p3/dpo_pause_owner
[ -f $N/state/p3/dpo_pending ] && mv $N/state/p3/dpo_pending $N/state/p3/dpo_pending.hold_owner
T=$(pgrep -f train_dpo.py | head -1); [ -n "$T" ] && kill -TERM $T && echo "train_term=$T"
sleep 25; pgrep -f train_dpo.py >/dev/null && { kill -9 $(pgrep -f train_dpo.py); echo kill9; }
sleep 20
if ! pgrep -af llama-server | grep -q -- '--port 8104.*--n-cpu-moe 0\b' && [ "$(pgrep -fc body_restart.sh)" = 0 ]; then
  C=$N/agent/autotrain/donor_hybrid.cmd.gpu_ncmoe0; [ -f $N/agent/autotrain/donor_hybrid.cmd.p5_best ] && C=$N/agent/autotrain/donor_hybrid.cmd.p5_best
  setsid nohup bash $N/ops/body_restart.sh --force --cmd $C 7>&- >/tmp/br_tp1.log 2>&1 < /dev/null & echo "br_started $(basename $C)"
fi
for i in $(seq 1 24); do sleep 10; [ "$(curl -s -o /dev/null -m 3 -w %{http_code} http://127.0.0.1:8104/health)" = 200 ] && pgrep -fc body_restart.sh | grep -q '^0$' && break; done
echo "h8104=$(curl -s -o /dev/null -m 3 -w %{http_code} http://127.0.0.1:8104/health) ncmoe=$(pgrep -af llama-server | grep -- '--port 8104' | grep -oE -- '--n-cpu-moe [0-9]+' | head -1) train=$(pgrep -fc train_dpo.py) vram=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)"
echo END
