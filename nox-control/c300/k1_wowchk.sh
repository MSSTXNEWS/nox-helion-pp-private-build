echo "K1: k1_wowchk"
B=http://127.0.0.1:18091/web; S=/workspace/nox/web/site
curl -s $B/chat-dc.html > /tmp/cdc.html; echo "served bytes=$(wc -c </tmp/cdc.html) md5=$(md5sum </tmp/cdc.html|cut -c1-8) site_md5=$(md5sum <$S/chat-dc.html|cut -c1-8) mtime=$(date -r $S/chat-dc.html +%m-%dT%H:%M)"
grep -oE '(src|href)="[^"]+\.(js|css)[^"]*"' /tmp/cdc.html | cut -d'"' -f2 | while read u; do case "$u" in http*) c=ext;; /*) c=$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:18091$u);; *) c=$(curl -s -o /dev/null -w %{http_code} $B/$u);; esac; echo "$c $u"; done | head -60
echo "--- wow assets on disk:"; ls $S | grep -iE "wow|cinematic|reveal|worlds|aurora|fx" | head -20
echo "--- chat pages:"; ls -la --time-style=+%m-%dT%H:%M $S | grep -E " chat[^ ]*\.html| resonance\.html| index\.html" | awk '{print $6,$5,$7}'
