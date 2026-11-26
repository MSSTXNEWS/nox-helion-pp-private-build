echo "C300: k2_a4"
N=/workspace/nox; ST=$N/state
pkill -f k2_restart_job.sh; sleep 1
python3 - <<'P'
f="/workspace/nox/state/k2_restart_job.sh"; s=open(f).read()
a="age=$(( $(date +%s) - $(stat -c %Y $N/state/orch/OWNER_ACTIVE) ))"
b="age=$(python3 -c \"import time;print(int(time.time()-float(open('$N/state/orch/OWNER_ACTIVE').read().split()[0])))\")"
print("ok" if a in s else "missing"); open(f,"w").write(s.replace(a,b))
P
python3 -c "import time;print('owner age now',int(time.time()-float(open('$N/state/orch/OWNER_ACTIVE').read().split()[0])))"
env RUNNER_TRACKING_ID=k2rs2 setsid -f bash $ST/k2_restart_job.sh </dev/null >/dev/null 2>&1
sleep 3; tail -2 $ST/k2_restart.log; tail -1 $ST/k2_dl.log; ls -la $N/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF | tail -1 | cut -c20-60
