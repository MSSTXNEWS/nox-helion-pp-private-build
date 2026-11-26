echo "C300: ch_dc15"
cb=$(date +%s); S=/workspace/nox/web/site
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/ensure.sh?cb=$cb") force 2>&1 | tail -4 | cut -c1-300
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
wc -c $S/nox-theme.js /workspace/nox/web/pkg/webroot/nox-theme.js
