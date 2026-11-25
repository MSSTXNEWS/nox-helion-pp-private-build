cd /workspace/nox/web/site
grep -n "lv-tag\|sl-select\|lv-inc" nox-chat-living.js | cut -c1-260 | sed 's/^/OUT: /' | head -20
