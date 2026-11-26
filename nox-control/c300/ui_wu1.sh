echo "C300: ui_wu1"
W=/workspace/nox/web
echo "== script"; cat $W/pkg/deploy/web_unify_s1.sh 2>&1 | head -40 | cut -c1-220
echo "== callers (grep)"; grep -rIl "web_unify_s1" /workspace/nox --include=*.sh --include=*.py --include=*.service --include=*.timer --include=*.json --include=*.yaml --include=*.yml --include=crontab 2>/dev/null | grep -v "/node_modules/\|/venv/\|\.bak" | head -20
grep -rIn "web_unify_s1" /workspace/nox/agent /workspace/nox/ops /workspace/nox/bin /etc/cron* /etc/systemd /etc/supervisor* 2>/dev/null | grep -v "\.bak" | cut -c1-240 | head -15
echo "== crontab"; crontab -l 2>&1 | head -20; ls /etc/cron.d 2>/dev/null
echo "== ps"; ps -eo pid,etimes,args | grep -E "unify|watchdog|run_web|nox_orch|nox_agents|chat_guard" | grep -v grep | cut -c1-160
echo "== webroot vs site"; cd $W; ls -d pkg/webroot 2>&1; for f in index.html chat.html nox-theme.js nox-u-ux.js nox-u-ux.css writer.html nav.json roles.json nox-wow-bg.js nox-nav.js nox-graphite.css; do a=$(stat -c '%Y %s' site/$f 2>/dev/null); b=$(stat -c '%Y %s' pkg/webroot/$f 2>/dev/null); [ "$a" = "$b" ] && echo "same $f" || echo "DIFF $f site=[$a] webroot=[$b]"; done
echo "== counts"; ls pkg/webroot | wc -l; ls site | grep -v "\.bak" | wc -l
