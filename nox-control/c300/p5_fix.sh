echo "K1: p5_fix"; export RUNNER_TRACKING_ID=""; N=/workspace/nox; A=$N/agent/autotrain
echo "t=$(date -u +%T) health=$(curl -s -m3 localhost:8104/health) free_mib=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)"
ps -eo pid,etimes,args | grep -E "body_restart|llama-server.*--port 81(04|44)" | grep -v grep | sed -E 's#(/[A-Za-z0-9_.-]+)+/#<d>/#g' | cut -c1-200
tail -4 $N/state/body_restart.log | cut -c1-200
if [ -z "$(curl -s -m3 localhost:8104/health)" ] && ! pgrep -f body_restart.sh >/dev/null; then
  setsid nohup bash $N/ops/body_restart.sh --force --cmd $A/donor_hybrid.cmd.liska_ncmoe22 --reason "p5 urgent restore" > /tmp/p5_fix.out 2>&1 < /dev/null &
  for i in $(seq 40); do sleep 5; curl -s -m2 localhost:8104/health | grep -q ok && break; done
  echo "after: health=$(curl -s -m3 localhost:8104/health) t=$(date -u +%T)"; tail -2 $N/state/body_restart.log | cut -c1-200
fi
echo END
