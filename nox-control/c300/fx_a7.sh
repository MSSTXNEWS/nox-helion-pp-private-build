P=/workspace/nox/web/pkg/server
echo ==registry; cat $P/svc_registry.json | head -60
echo ==grep; grep -n "/api/\|'/music\|\"/music\|/memory/\|/glm/\|svc_proxy\|def do_GET\|def _route\|startswith(\"/\|startswith('/" $P/web_server.py | cut -c1-200 | head -80
wc -l $P/web_server.py $P/svc_proxy.py
echo ==run; cat $P/run_web.sh; ls -la /workspace/nox/web/site | head -3; readlink -f /workspace/nox/web/site
grep -n "music" $P/*.py | cut -c1-160 | head
