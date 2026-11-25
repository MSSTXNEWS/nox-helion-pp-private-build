echo "C300: k2_qa1"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
for u in /index.html /web/ /web/index.html /web/site/index.html; do for p in 8090 4100; do echo "$p$u $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$p$u)"; done; done
grep -rn "8090\|4100" /workspace/nox/web/pkg/server/run_web.sh | cut -c1-200 | head -3
exit 0
