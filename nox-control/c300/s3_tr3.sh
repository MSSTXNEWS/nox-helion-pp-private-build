S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
echo "== TR3"; grep -c "nox-ds.css" $S/training.html
cp $S/nox-ds.css $S/nox-ds.css.bak_s3_24
grep -q "S3 слой-карточек v3" $S/nox-ds.css || cat >> $S/nox-ds.css <<'C'

/* S3 слой-карточек v3: повышенная специфичность, чтобы стили страниц (training и др.) не возвращали прозрачность */
html body .card.card.card.card:has(canvas),html body .card.card.card.card:has(table),html body .card.card.card.card:has(.chart),html body section.card.card.card.card:has(canvas){background-color:rgba(12,9,9,.96)!important;background-image:none!important}
C
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_tr3.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for pgn in ('training','system','memory','dispatcher','models'):
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(5000)
        print('R:',pgn,pg.evaluate("()=>[...document.querySelectorAll('.card')].filter(c=>c.querySelector('canvas,table')).slice(0,3).map(c=>getComputedStyle(c).backgroundColor)"))
        if pgn=='training':
            pg.screenshot(path='/tmp/s.png'); subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/s.png','-vf','scale=1000:-1','-q:v','8','/tmp/s.jpg'])
            print('B64_BEGIN'); print(base64.b64encode(open('/tmp/s.jpg','rb').read()).decode()); print('B64_END')
        ctx.close()
    b.close()
P
timeout 120 $PY -I /tmp/s3_tr3.py 2>&1 | fold -w 900
