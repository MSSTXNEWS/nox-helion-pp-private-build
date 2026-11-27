echo "K1: l1_slot4"
grep -n "BASE\|def \|urlopen\|HTTPConnection" /workspace/nox/integration/adapter.py | cut -c1-170 | head -60
