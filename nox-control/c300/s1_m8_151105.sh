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
cd /tmp; /workspace/nox/venv/bin/python /tmp/one.py finance.html 1440 900 m_fin14 "$(cat <<'JSEOF'
(()=>{const b=document.querySelector('.nai-btn');if(!b)return;const r=b.getBoundingClientRect();const o=[];document.querySelectorAll('header,nav,.dock,#dock,[class*=head],[class*=dock]').forEach(e=>{const s=getComputedStyle(e);if(s.position!=='fixed'&&s.position!=='sticky')return;const q=e.getBoundingClientRect();if(q.width&&q.left<r.right&&q.right>r.left&&q.top<r.bottom&&q.bottom>r.top)o.push((e.id||e.className).toString().slice(0,20))});const d=document.createElement('div');d.style.cssText='position:fixed;left:0;top:300px;z-index:99999;background:#000;color:#0f0;font:14px monospace;padding:4px';d.textContent='btn '+Math.round(r.left)+','+Math.round(r.top)+','+Math.round(r.right)+','+Math.round(r.bottom)+' vh'+innerHeight+' ovl:'+o.join('|');document.body.appendChild(d)})()
JSEOF
)" 2>&1
