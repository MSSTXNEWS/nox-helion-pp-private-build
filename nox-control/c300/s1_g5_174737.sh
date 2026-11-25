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
cd /tmp; /workspace/nox/venv/bin/python /tmp/one.py chat.html 1366 768 g_rq2 "$(cat <<'JSEOF'
(async()=>{const W=ms=>new Promise(r=>setTimeout(r,ms));await W(4500);const send=t=>{const i=document.querySelector('#input');i.value=t;i.dispatchEvent(new Event('input',{bubbles:true}));setTimeout(()=>document.querySelector('#btnSend').click(),80)};send('/статус');await W(5500);const a=[...document.querySelectorAll('#msgs .m.a .rq-act')].pop();if(a){a.click()}await W(600);send('Спасибо, понял');await W(2500);const d=document.createElement('div');d.style.cssText='position:fixed;left:0;top:90px;z-index:99999;background:#000;color:#0f0;font:14px monospace;padding:4px';d.textContent='quote='+(document.querySelector('.rq-in')?document.querySelector('.rq-in').textContent:'none');document.body.appendChild(d)})()
JSEOF
)" 2>&1
