echo "C300: ch_r3"
cd /workspace/nox/web/site
F="chat.html nox-chat-c.css nox-chat-clean.css nox-chat-clean.js nox-chat-demo.js nox-chat-kanban.js nox-chat-rq.js nox-chat-wow.css nox-chat-wow.js nox-dock-pop.js nox-dock-wow.js nox-k4-core.js nox-hud-s1.css nox-k8-ui.css nox-m-mobile.css nox-nav.js nox-theme.js nox-vt.css nox-wow-bg.js nox-graphite-map.css nox-u-board.js nox-ux-fab.js nox-pages.css nox-ghost-all.js nox-u-a11y.js nox-u-pad.js nox-k8-meta.js nox-graphite.css nox-unify.css"
F2=""; for f in $F; do [ -f $f ] && F2="$F2 $f"; done
tar czf /tmp/ch_r3.tgz $F2; ls -l /tmp/ch_r3.tgz
echo "==B64"; base64 -w0 /tmp/ch_r3.tgz; echo; echo "==END"
