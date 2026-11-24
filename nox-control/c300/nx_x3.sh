S=/workspace/nox/web/site; curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/assets/nox-ninja.js?t=$(date +%s)" -o $S/nox-ninja.js
/workspace/nox/venv/bin/python /workspace/nox/svc/nox_index.py 2>&1 | tail -2
curl -s -m5 "localhost:8091/search?q=календарь" | head -c 300; echo
ls /workspace/nox/state/web | head -5
