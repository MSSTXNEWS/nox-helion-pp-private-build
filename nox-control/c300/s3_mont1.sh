S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
cp $S/nox-ds.css $S/nox-ds.css.bak_s3_22
grep -q "S3 select-arrow" $S/nox-ds.css || cat >> $S/nox-ds.css <<'C'

/* S3 select-arrow: стрелка у select поверх стилей страниц */
html select{appearance:none!important;-webkit-appearance:none!important;padding-right:38px!important;background-repeat:no-repeat!important;background-position:right 12px center!important;background-size:16px!important;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23e9b465' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")!important}
C
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_mont1.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); names=[]
    for pgn in ('index','cinema','settings','chat'):
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(5500)
        pg.screenshot(path='/tmp/m_%s.png'%pgn); names.append('/tmp/m_%s.png'%pgn); ctx.close()
    b.close()
cmd=['ffmpeg','-loglevel','error','-y']
for n in names: cmd+=['-i',n]
cmd+=['-filter_complex','[0]scale=700:-1[a];[1]scale=700:-1[b];[2]scale=700:-1[c];[3]scale=700:-1[d];[a][b]hstack[x];[c][d]hstack[y];[x][y]vstack','-q:v','9','/tmp/mont.jpg']
subprocess.run(cmd)
print('B64_BEGIN'); print(base64.b64encode(open('/tmp/mont.jpg','rb').read()).decode()); print('B64_END')
P
timeout 150 $PY -I /tmp/s3_mont1.py 2>&1 | fold -w 900
