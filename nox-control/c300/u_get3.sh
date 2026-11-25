echo "C300: u_get3"
O=/workspace/nox/agent/out; cat $O/u_qaa_prog.txt 2>/dev/null; ls -la $O | grep u_qaa; pgrep -f qa_audit | head -2; tail -c 600 $O/u_qaa_1.out
python3 - <<'PYX'
import json,glob
for f in sorted(glob.glob('/workspace/nox/agent/out/u_qaa_*.json')):
    d=json.load(open(f));print(f.split('/')[-1],type(d).__name__);print(json.dumps(d,ensure_ascii=False)[:1500])
PYX
