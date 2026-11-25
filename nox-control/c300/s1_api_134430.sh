cd /workspace/nox/web/site; grep -n "fetch(" nox-minichat.js | cut -c1-260 | head -8; echo ===; grep -n "api/chat\|/api/turn" nox-minichat.js | cut -c1-300 | head -8; wc -c nox-minichat.js
