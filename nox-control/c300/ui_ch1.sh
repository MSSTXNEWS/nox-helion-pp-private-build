echo "C300: ui_ch1 (скрины чата)"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/chs.py <<'PEOF'
import io,base64
from playwright.sync_api import sync_playwright
from PIL import Image
with sync_playwright() as p:
    b=p.chromium.launch()
    for W,H in((1440,900),(390,844)):
        c=b.new_context(viewport={'width':W,'height':H},is_mobile=(W<500),has_touch=(W<500)); x=c.new_page()
        x.route('**/api/nox/outbox*',lambda r:r.fulfill(status=200,content_type='application/json',body='{"messages":[]}'))
        x.goto('http://127.0.0.1:8091/web/chat-dc.html',wait_until='load',timeout=60000); x.evaluate("localStorage.setItem('nox.wow.cur','qa-ch1%d')"%W); x.reload(); x.wait_for_timeout(4000)
        im=Image.open(io.BytesIO(x.screenshot(type='png'))).convert('RGB'); im.thumbnail((1000,1000)); buf=io.BytesIO(); im.save(buf,'JPEG',quality=60); s=base64.b64encode(buf.getvalue()).decode()
        for i in range(0,len(s),3000): print('B64 ch%d %d %s'%(W,i//3000,s[i:i+3000]),flush=True)
        c.close()
    b.close()
PEOF
timeout 120 $PY /tmp/chs.py
