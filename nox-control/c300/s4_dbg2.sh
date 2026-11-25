S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-projects.js nox-s4-projects.css nox-s4-grafana.js; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f; done; grep -c "pc.cpu.percent" nox-s4-grafana.js
grep -rn "empty text" /workspace/nox /root/nox --include=*.py -l 2>/dev/null | head -3
F=$(grep -rln "empty text" /workspace/nox /root/nox --include=*.py 2>/dev/null | head -1); grep -n "empty text" -B12 $F | head -40 | cut -c1-200
grep -n "op:" nox-p-memory.js | head -8 | cut -c1-200
curl -s -m5 -X POST -H 'Content-Type: application/json' -d '{"op":"health"}' 127.0.0.1:8091/memory/api | head -c 200
