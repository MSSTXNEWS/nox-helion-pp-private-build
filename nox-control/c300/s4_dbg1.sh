echo S4RUN:s4_dbg1
S=/workspace/nox/web/site
cd $S; grep -c s4 system.html dispatcher.html training.html; head -c 300 nox-s4-grafana.js; grep -c "pc.cpu.percent" nox-s4-grafana.js
grep -n "echarts\|<script" system.html | cut -c1-160
echo == memory api
grep -n "memory(" nox-api.js | head -5 | cut -c1-300; grep -n "export.*function memory\|const memory" -A6 nox-api.js | head -14 | cut -c1-300
curl -s -m5 -X POST -H 'Content-Type: application/json' -d '{"op":"journal","limit":500}' 127.0.0.1:8091/memory/api | head -c 300; echo
curl -s -m5 -X POST -H 'Content-Type: application/json' -d '{"op":"journal","limit":50}' 127.0.0.1:8091/memory/api | head -c 200; echo
grep -n "def.*journal\|op ==\|\"op\"" /workspace/nox/*/recall_api.py 2>/dev/null | head; find /workspace/nox /root/nox -name recall_api.py 2>/dev/null | head -2
