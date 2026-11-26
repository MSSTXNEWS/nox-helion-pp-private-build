echo "C300: srv_k63"
cd /workspace/nox
sed -n '120,143p' brain/SLP/fidelity_cases.py | cut -c1-200
grep -n "^def score" -A32 brain/SLP/fidelity_test.py | cut -c1-200 | head -50
grep -n "^def rule_check" -A22 brain/SLP/fidelity_test.py | cut -c1-200 | head -30
sed -n '20,30p;157,176p;329,340p' ops/liska_gates.py | cut -c1-200
grep -n "^import\|^from\|sys.path" ops/liska_gates.py | head
