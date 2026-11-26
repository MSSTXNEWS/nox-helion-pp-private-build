echo "C300: k2_r20"
F=/workspace/nox/stewards/owner_active.py; wc -l $F
sed -n 1,60p $F | cut -c1-240
tail -5 /workspace/nox/state/orch/owner_active.log | cut -c1-200
