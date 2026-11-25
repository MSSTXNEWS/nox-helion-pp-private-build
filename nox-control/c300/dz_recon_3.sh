W=/workspace/nox/web/pkg/server
grep -rn "_c300_vision\|def _img_generate\|NOX_ALLOW_GLM_DIRECT" $W/*.py | head | cut -c1-160
F=$(grep -ln "def _c300_vision" $W/*.py | head -1); echo F=$F
sed -n "$(grep -n 'def _c300_vision' $F | head -1 | cut -d: -f1),+45p" $F | cut -c1-240
grep -n "def _img_generate" -A14 $W/web_server.py | cut -c1-220
tr '\0' '\n' < /proc/$(pgrep -f "python web_server.py"|head -1)/environ | grep -o "^NOX_[A-Z_]*=" | head -30
curl -s -m 5 -X POST localhost:8091/img/generate -H 'content-type: application/json' -d '{"prompt":"x"}' | head -c 300; echo
curl -s -m 5 localhost:8091/img/health | head -c 200; echo
ls $W/../../site/qa/rework/creative.fixed | head
