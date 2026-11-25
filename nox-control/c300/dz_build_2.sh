S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
[ -f $S/creative.html.bak_dz_1 ] || cp $S/creative.html $S/creative.html.bak_dz_1
for f in nox-dz-creative.js nox-dz-creative.css; do curl -fsSL "$R/$f?$(date +%s)" -o $S/$f || echo FAIL $f; done
curl -fsSL "$R/dz_creative.html?$(date +%s)" -o $S/creative.html || echo FAIL html
curl -fsSL "$R/dz_qa.py?$(date +%s)" -o /tmp/dz_qa.py
ls -la $S/nox-dz-creative.* $S/creative.html
echo "== icons missing"; for n in $(grep -o "name=\"[a-z0-9-]*\"\|ib('[a-z0-9-]*'" $S/nox-dz-creative.js | sed "s/name=\"//;s/ib('//;s/[\"']//g" | sort -u); do [ -f $S/vendor/shoelace/cdn/assets/icons/$n.svg ] || echo MISSING $n; done
ls $S/vendor/sortablejs | head -5
PY=/workspace/nox/venv/bin/python; $PY -c "import playwright" 2>/dev/null || PY=python3
timeout 280 $PY /tmp/dz_qa.py 2>&1 | cut -c1-70000 | sed 's/^/OUT: /' | tail -40
