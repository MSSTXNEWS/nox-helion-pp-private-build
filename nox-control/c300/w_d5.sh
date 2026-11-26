echo "C300: w_d5"
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
mkdir -p /tmp/w18; for f in diag_page small_scan2; do curl -fsSL "$R/w_a11y/$f.py?cb=$(date +%s)" > /tmp/w18/$f.py; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
echo "== diag writer tv"; timeout 90 $N/venv/bin/python /tmp/w18/diag_page.py writer tv 2>&1 | cut -c1-500
echo "== small qa photo"; timeout 120 $N/venv/bin/python /tmp/w18/small_scan2.py qa photo 2>&1 | cut -c1-700 | head -12
echo "== tv lh bp"; python3 - <<'P'
import json,glob
for f in glob.glob('/workspace/nox/agent/out/ui_sc/tv_*'):
    s=open(f).read()
    try:
        d=json.loads(s); print(f.split('/')[-1], json.dumps(d,ensure_ascii=False)[:600])
    except Exception: print(f,s[:200])
P
