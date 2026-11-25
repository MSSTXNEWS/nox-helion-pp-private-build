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
cd /tmp; /workspace/nox/venv/bin/python /tmp/one.py chat.html 390 844 t_mob "$(cat <<'JSEOF'
(()=>{const n=Date.now(),H=36e5;const T=(id,t,ago,q)=>({id,title:t,ts:n-ago,msgs:[{role:'user',content:q,ts:n-ago},{role:'assistant',content:'Ответ NOX на: '+q,ts:n-ago}],srv:''});localStorage.setItem('nox.wow.threads',JSON.stringify([T('a1','Проверка ядра',H,'Проверь ядро'),T('a2','План на день',2*H,'Составь план'),T('a3','Вчера: ошибки',30*H,'Разбери ошибки'),T('a4','Старый диалог',200*H,'Привет'),T('a5','Идеи для главной',3*H,'Дай идеи')]));localStorage.setItem('nox.tg.pins',JSON.stringify(['a3']));location.reload();})()
JSEOF
)" 2>&1
