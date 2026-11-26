echo "C300: ui_sync2"
curl -fsSL --retry 5 https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh -o /tmp/webroot_sync.sh && bash /tmp/webroot_sync.sh
W=/workspace/nox/web; for f in index.html chat.html nox-u-ux.js writer.html nav.json nox-theme.js; do cmp -s $W/site/$f $W/pkg/webroot/$f && echo "same $f" || echo "DIFF $f"; done
ls $W/pkg/webroot | wc -l
