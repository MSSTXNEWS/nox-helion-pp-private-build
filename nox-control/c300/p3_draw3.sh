W=/workspace/nox/web/pkg/server
grep -rn "_c300_img_file" $W/*.py | head -3 | cut -c1-120
f=$(grep -ln "def _c300_img_file" $W/*.py | head -1); n=$(grep -n "def _c300_img_file" $f | cut -d: -f1); sed -n "${n},$((n+30))p" $f | cut -c1-200
echo "== /img/generate success sample (sun_adapter _save_png)"; sed -n 300,330p /workspace/nox/ops/sun_adapter/sun_adapter.py | cut -c1-170
echo "== img file dirs"; ls -d /workspace/nox/state/graphics* /workspace/nox/state/img* /workspace/nox/data/graphics* 2>/dev/null; ls /workspace/nox/state/advisor_images | tail -2
echo "== chat auth for /api/chat test?"; grep -n -E "auth|Authorization|cookie" $W/web_server.py | head -6 | cut -c1-150
