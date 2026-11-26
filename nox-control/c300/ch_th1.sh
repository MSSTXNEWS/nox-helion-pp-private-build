echo "C300: ch_th1"
S=/workspace/nox/web/site; ls -l --time-style=+%m-%d_%H:%M $S/nox-theme.js $S/nox-wow-bg.js $S/nox-graphite.css | cut -c20-120
curl -s -m5 localhost:8091/web/chat.html | grep -c "data-nox-theme\|nox-graphite"; curl -s -m5 localhost:8091/web/nox-theme.js | wc -c
tail -c 300 /workspace/nox/state/ch_audit1.log
