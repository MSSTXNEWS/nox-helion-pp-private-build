echo "C300: ch_gold1"
cb=$(date +%s); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1/golden.py?cb=$cb" -o /tmp/golden.py && grep -q VERIFIED /tmp/golden.py || { echo STALE; exit 0; }
setsid -f python3 /tmp/golden.py > /workspace/nox/state/ch_golden.out 2>&1 < /dev/null; echo started
python3 -I -c "
import json;d=json.load(open('/workspace/nox/web/site/qa/audit.json'))['chat'];print(d.get('ts'));[print('-',f['item'][:90],'|',str(f['detail'])[:200]) for f in d.get('fails',[])]"
