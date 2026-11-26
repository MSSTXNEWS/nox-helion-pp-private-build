echo "C300: k2_a8"
N=/workspace/nox; F=$N/ops/body_restart.sh
cp -n $F $F.bak_k2
python3 - <<'P'
f="/workspace/nox/ops/body_restart.sh"; s=open(f).read()
a='setsid nohup "${ARGS[@]}" > $OUT/donor_donor_$MODE.log 2>&1 < /dev/null &'
b='setsid nohup "${ARGS[@]}" > $OUT/donor_donor_$MODE.log 2>&1 < /dev/null 9>&- &'
print("patched" if a in s else "missing"); open(f,"w").write(s.replace(a,b))
P
mv $N/state/body_restart.lock $N/state/body_restart.lock.stale_k2; sleep 25; tail -4 $N/state/k2_job3.log | cut -c1-200
