echo "C300: ui_wu2"; P=/workspace/nox/web/pkg
for f in server/web_watchdog.sh server/run_web.sh; do echo "=== $f ($(stat -c '%y' $P/$f | cut -c1-16))"; grep -nE "webroot|cp -a|rsync|unify|site|restore|git " $P/$f | cut -c1-230 | head -25; done
echo "== other scripts mentioning webroot"; grep -rIln "pkg/webroot\|webroot/\." /workspace/nox/ops /workspace/nox/agent /workspace/nox/stewards /workspace/nox/operators /workspace/nox/web/pkg --include=*.sh --include=*.py 2>/dev/null | grep -v "\.bak" | head -15
echo "== logs web_boot/watchdog around"; tail -5 /workspace/nox/agent/out/web_boot.log 2>/dev/null | cut -c1-200; ls -la /workspace/nox/web/pkg/server/*.log /workspace/nox/logs/*watchdog* 2>/dev/null | head
