echo "C300: c_fetch4"
cut -c1-700 /workspace/nox/state/c_acc2.out | grep -v "^+" | tail -60
echo "== pipe_err"; tail -15 /workspace/nox/state/pipe_err.log 2>&1
