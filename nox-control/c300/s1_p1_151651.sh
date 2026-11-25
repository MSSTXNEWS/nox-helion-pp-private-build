cat > /tmp/one.py <<'PYEOF'
import asyncio,base64,textwrap,sys
from playwright.async_api import async_playwright
page,w,h,tag=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),sys.argv[4]; js=sys.argv[5] if len(sys.argv)>5 else ''
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
        pg=await b.new_page(viewport={'width':w,'height':h},device_scale_factor=1); 
        await pg.goto('http://localhost:8091/web/'+page,wait_until='domcontentloaded',timeout=40000); await pg.wait_for_timeout(9000)
        if js:
            await pg.evaluate(js); await pg.wait_for_timeout(9000 if 'reload' in js else 2500)
        await pg.screenshot(path='/tmp/one.jpg',type='jpeg',quality=14)
        import subprocess,os
        if w>1500 or os.path.getsize('/tmp/one.jpg')>44000: subprocess.run(['ffmpeg','-y','-loglevel','error','-i','/tmp/one.jpg','-vf','scale=960:-1','-q:v','9','/tmp/one2.jpg']); import shutil; shutil.move('/tmp/one2.jpg','/tmp/one.jpg')
        d=base64.b64encode(open('/tmp/one.jpg','rb').read()).decode(); print('B64_%s_BEGIN'%tag);print('\n'.join(textwrap.wrap(d,200)));print('B64_%s_END'%tag)
        await b.close()
asyncio.run(main())
PYEOF
cd /tmp; /workspace/nox/venv/bin/python /tmp/one.py pdf.html 1440 900 m_pdfreal "$(cat <<'JSEOF'
(async()=>{const s='%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length 44>>stream\nBT /F1 24 Tf 30 100 Td (NOX PDF TEST) Tj ET\nendstream endobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R/Size 6>>\n%%EOF';const f=new File([s],'t.pdf',{type:'application/pdf'});const dt=new DataTransfer();dt.items.add(f);const i=document.querySelector('#pdfFile');i.files=dt.files;i.dispatchEvent(new Event('change',{bubbles:true}));await new Promise(r=>setTimeout(r,4000))})()
JSEOF
)" 2>&1
