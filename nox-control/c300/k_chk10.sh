echo "C300: k_chk10"
S=/workspace/nox/web/site
ls -la --time-style=+%m-%d_%H:%M $S/nox-theme.js $S/chat.html $S/nox-wow-bg.js $S/nox-graphite.css
grep -c graphite $S/nox-theme.js; grep -o "nox.ui.theme[^;]\{0,120\}" $S/nox-theme.js | head -3
grep -o '<html[^>]*>' $S/chat.html; grep -o 'nox-theme.js[^"]*\|nox-graphite[^"]*\|nox-chat-clean[^"]*' $S/chat.html | sort -u
ps -eo pid,lstart,args | grep -E "[w]eb_unify|[r]un_web" | head
crontab -l 2>/dev/null | grep -i "unify\|web" | head
