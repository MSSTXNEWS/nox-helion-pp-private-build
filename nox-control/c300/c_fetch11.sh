echo "C300: c_fetch11"
echo "== race3"; cut -c1-500 /workspace/nox/state/c_race3.out | grep -v "^+" | tail -25
echo "== race1 tail (audit)"; tail -c 2600 /workspace/nox/state/c_race1.out | grep -v "^+"
pgrep -fa qa_audit | cut -c1-100
