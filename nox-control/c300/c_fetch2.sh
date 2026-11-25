echo "C300: c_fetch2"
echo "== fix1 log"; grep -v "^+" /workspace/nox/state/c_fix1.log | tail -15 | cut -c1-300
echo "== test2"; cut -c1-1000 /workspace/nox/state/c_test2.out | tail -40
