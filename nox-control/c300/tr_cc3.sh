export RUNNER_TRACKING_ID=""
echo "C300: tr_cc3"
F=/workspace/nox/web/pkg/server/chat_core.py
echo "#### 454-462"; sed -n 454,462p $F | cut -c1-300
echo "#### 612-700"; sed -n 612,700p $F | cut -c1-250
echo "#### draw"; grep -n "draw_request\|def .*draw\|_via_draw\|img/gen\|image_event\|\"image\"" $F | cut -c1-200 | head -20
grep -rn "def draw_request" /workspace/nox/web/pkg/server/*.py | cut -c1-160
echo END
