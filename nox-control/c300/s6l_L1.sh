echo "K1: s6l_L1 (deploy life_time module + canon recon)"
D=$(dirname "$0")/s6l_files; M=/workspace/nox/mods
cp $D/life_time.py $M/life_time.py && mkdir -p $M/tests && cp $D/test_life_time.py $M/tests/
cd $M && python3 -I tests/test_life_time.py 2>&1 | tail -4
C=/workspace/nox/canon/canon.py
python3 - <<PY
import ast
s=open("$C",encoding="utf-8").read(); t=ast.parse(s)
for n in ast.walk(t):
    if isinstance(n,ast.FunctionDef) and any(k in n.name.lower() for k in ("morning","evening","brief","tick","main","ritual")):
        print("def",n.name,"line",n.lineno,"-",n.end_lineno,"args",[a.arg for a in n.args.args])
PY
grep -n "morning_brief_v5\|evening_brief_v5\|08:00\|22:30\|hour ==\|minute ==" $C | cut -c1-160 | head -20
echo "p0 callers:"; grep -rn "initiative(" /workspace/nox/agent/nox_agents --include=*.py | cut -c1-140 | head -5
echo END
