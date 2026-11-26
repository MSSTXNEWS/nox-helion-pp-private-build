echo "C300: k_th10"
grep -rn "webroot\|site" /workspace/nox/web/pkg/server/run_web.sh /workspace/nox/web/pkg/deploy/* 2>/dev/null | grep -v "^.*#" | head -15
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite
curl -fsSL --retry 5 --retry-all-errors "$R/ensure.sh?cb=$(date +%s)" -o /tmp/th_ensure.sh && timeout 200 bash /tmp/th_ensure.sh force 2>&1 | tail -6
S=/workspace/nox/web/site; W=/workspace/nox/web/pkg/webroot; TS=$(date +%s)
if grep -q graphite $S/nox-theme.js; then
  mkdir -p /workspace/nox/web/pkg_webroot_bak_$TS
  for f in nox-theme.js nox-wow-bg.js nox-nav.js nox-graphite.css nox-graphite-map.css nox-motion.css nox-motion.js nox-th-fix.css nox-icons.js nox-logo.svg; do
    [ -f $W/$f ] && cp -p $W/$f /workspace/nox/web/pkg_webroot_bak_$TS/; [ -f $S/$f ] && cp $S/$f $W/$f; done
  [ -f /workspace/nox/web/pkg/src/wow/nox-theme.js ] && cp $S/nox-theme.js /workspace/nox/web/pkg/src/wow/nox-theme.js
  echo "PKG_SYNCED"
fi
ls -la --time-style=+%m-%d_%H:%M $S/nox-theme.js $W/nox-theme.js
curl -s -m 8 http://127.0.0.1:8091/web/nox-theme.js | grep -c graphite
