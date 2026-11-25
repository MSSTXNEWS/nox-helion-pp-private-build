echo S4RUN:s4_kb1
cd /workspace/nox/web/site; curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src/nox-s4-brain.css?t=$(date +%s)" -o nox-s4-brain.css
for u in svc/kuma/metrics svc/kuma/api/entry-page svc/kuma/api/status-page/default svc/beszel/api/health svc/beszel/api/collections/systems/records svc/memos/api/v1/workspace/profile; do echo "-- $u $(curl -s -m6 -o /tmp/kb.out -w '%{http_code}' 127.0.0.1:8091/$u)"; head -c 200 /tmp/kb.out; echo; done
