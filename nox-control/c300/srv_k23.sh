echo "C300: srv_k23"
cd /workspace/nox/distill_v2/code
sed -n '2490,2550p' distill_v2.py | cut -c1-230
grep -n "def round_gates" -A25 liska_gates.py | cut -c1-200 | head -45
grep -n "def gate_persona\|gate_persona =" distill_v2.py | head -3
grep -n "def chatml\|^THINK\|THINK =" distill_v2.py | head
sed -n '1575,1600p' distill_v2.py | cut -c1-230
