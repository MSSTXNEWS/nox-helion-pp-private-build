cat > /tmp/one.py <<'PYEOF'
import asyncio,base64,textwrap,sys
from playwright.async_api import async_playwright
page,w,h,tag=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),sys.argv[4]; js=sys.argv[5] if len(sys.argv)>5 else ''
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
        pg=await b.new_page(viewport={'width':w,'height':h},device_scale_factor=1); 
        await pg.goto('http://localhost:8091/web/'+page,wait_until='domcontentloaded',timeout=40000); await pg.wait_for_timeout(9000)
        if js: await pg.evaluate(js); await pg.wait_for_timeout(2500)
        await pg.screenshot(path='/tmp/one.jpg',type='jpeg',quality=22)
        import subprocess
        if w>1500: subprocess.run(['ffmpeg','-y','-loglevel','error','-i','/tmp/one.jpg','-vf','scale=1100:-1','-q:v','9','/tmp/one2.jpg']); import shutil; shutil.move('/tmp/one2.jpg','/tmp/one.jpg')
        d=base64.b64encode(open('/tmp/one.jpg','rb').read()).decode(); print('B64_%s_BEGIN'%tag);print('\n'.join(textwrap.wrap(d,200)));print('B64_%s_END'%tag)
        await b.close()
asyncio.run(main())
PYEOF
cd /tmp; /workspace/nox/venv/bin/python /tmp/one.py money.html 1440 900 d_mo "$(cat <<'JSEOF'
document.querySelector('#fiDemo')&&document.querySelector('#fiDemo').click()
JSEOF
)" 2>&1
