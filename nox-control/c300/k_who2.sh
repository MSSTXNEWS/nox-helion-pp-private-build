echo "C300: k_who2"
S=/workspace/nox/web/site
stat -c "%s %y %z %n" $S/nox-theme.js /workspace/nox/web/pkg/webroot/nox-theme.js
ps -eo pid,etimes,args | grep -iE "[s]yncthing|[u]nison|[l]sync|[i]notify|[r]clone" | cut -c1-200 | head
for c in /root/.config/syncthing/config.xml /root/.local/state/syncthing/config.xml /workspace/*/syncthing*/config.xml; do [ -f $c ] && { echo "== $c"; grep -o '<folder [^>]*path="[^"]*"' $c | head; }; done
grep -rln "web/site\|webroot" /workspace/nox/agent/*.sh /etc/cron* /var/spool/cron 2>/dev/null | head -20
crontab -l 2>/dev/null | head -40
