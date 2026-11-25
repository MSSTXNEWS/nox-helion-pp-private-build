S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server
echo "== p-training"; head -c 3500 $S/nox-p-training.js
echo "== nox-cmd.js"; head -c 3000 $S/nox-cmd.js
echo "== web cmd"; grep -n -B2 -A25 '"/api/cmd"' $P/web_server.py | head -90
echo "== minichat ctx"; grep -n -i -E "context|page|body.dataset|system" $S/nox-minichat.js | head -25
echo "== notify"; head -c 1500 $S/nox-notify.js
echo "== outbox"; curl -s -m5 localhost:8091/api/nox/outbox | head -c 600
echo; curl -s -m5 localhost:8091/api/nox/status | head -c 500
echo "== ntfy"; ls $P | head -30; grep -rn -i ntfy $P/*.py | head -8
echo "== events api"; curl -s -m5 localhost:8091/api/nox-live | head -c 400
