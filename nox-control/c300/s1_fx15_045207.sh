mkdir -p /workspace/nox/tools
cat > /workspace/nox/tools/s1_shot.py <<'S1PY'
import base64,subprocess,sys,json,time
from playwright.sync_api import sync_playwright
# usage: s1_shot.py page label [send] [vp=pc,4k,mob]
page=sys.argv[1]; L=sys.argv[2]; opts=sys.argv[3:]
send='send' in opts
vps=[('pc',1440,900,0),('4k',3840,2160,0),('mob',390,844,1)]
sel=[o.split('=')[1] for o in opts if o.startswith('vp=')]
if sel: vps=[v for v in vps if v[0] in sel[0].split(',')]
def out(tag,png,w):
    j='/tmp/s_%s.jpg'%tag
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v','11',j])
    for suf,q in (('',11),('b',16)):
        subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v',str(q),j])
        b=base64.b64encode(open(j,'rb').read()).decode()
        print('B64_%s%s_BEGIN'%(tag,suf))
        for i in range(0,len(b),900): print(b[i:i+900])
        print('B64_%s%s_END'%(tag,suf))
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--ignore-gpu-blocklist'])
    for name,w,h,mob in vps:
        ctx=b.new_context(viewport={'width':w,'height':h},has_touch=bool(mob),is_mobile=bool(mob))
        pg=ctx.new_page(); errs=[]; bad=[]
        pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
        pg.on('response',lambda r:bad.append('%d %s'%(r.status,r.url[-90:])) if r.status>=400 else None)
        pg.on('requestfailed',lambda r:bad.append('FAIL '+r.url[-90:]))
        if 'seed' in opts:
            import json as J
            md="Вот пример ответа.\n\n- пункт один\n- пункт два\n\n```python\nprint('привет')\n```\n\nФормула: $E=mc^2$\n\n$$\\int_0^1 x^2dx=\\frac13$$\n\n```mermaid\ngraph LR; A[Вопрос]-->B[Ядро]; B-->C[Ответ]\n```"
            th=[{'id':'seed-1','title':'Проверка разметки','ts':1795576425326,'msgs':[{'role':'user','content':'Покажи пример кода, формулу и схему','ts':1795576431803,'att':[]},{'role':'assistant','content':md,'ts':1795576431822,'via':'УРОВЕНЬ: НОКС'},{'role':'user','content':'Спасибо, а теперь коротко','ts':1795576531803,'att':[]},{'role':'assistant','content':'Готово: код, формула и схема выше.','ts':1795576531822}],'srv':False}]
            ctx.add_init_script("try{localStorage.setItem('nox.wow.threads',%s)}catch(e){}"%J.dumps(J.dumps(th)))
        pg.goto('http://localhost:8091/web/'+page,wait_until='load'); pg.wait_for_timeout(6000)
        if send and name=='pc':
            try:
                pg.evaluate("document.querySelector('#modes [data-m=fast]').click()"); pg.fill('#input','привет, ответь коротко одной строкой'); pg.keyboard.press('Enter')
                for i in range(30):
                    pg.wait_for_timeout(2000)
                    t=pg.evaluate("(()=>{const a=[...document.querySelectorAll('#msgs .m.a .txt')].pop();return a?a.innerText:''})()")
                    if t and 'ОЖИДАНИЕ' not in t and not pg.evaluate("document.body.classList.contains('nox-busy')"): break
                print('REPLY',json.dumps(t,ensure_ascii=False)[:300])
                print('LSTHREADS',(pg.evaluate("localStorage.getItem('nox.wow.threads')") or '')[:700])
                print('BUBBLE_ERR',pg.evaluate("!!document.querySelector('.bubble.err')"))
            except Exception as e: print('SENDERR',e)
        if send and name=='pc':
            try: pg.hover('#msgs .m.a .bubble'); pg.wait_for_timeout(500)
            except Exception as e: print('HOVERERR',str(e)[:80])
        if name=='pc' and 'qhelp' in opts:
            print('FIXED',pg.evaluate("[...document.querySelectorAll('body *')].filter(e=>{const c=getComputedStyle(e);const r=e.getBoundingClientRect();return c.position=='fixed'&&r.width<70&&r.width>20&&r.left<80&&r.top>600}).map(e=>e.outerHTML.slice(0,200)).join('\\n')"))
        if 'busy' in opts: pg.evaluate("document.body.classList.add('nox-busy')"); pg.wait_for_timeout(3500)
        pg.screenshot(path='/tmp/s.png')
        out(L+'_'+name,'/tmp/s.png',1100 if w>1500 else w)
        if 'slash' in opts and name=='pc':
            pg.fill('#input','/'); pg.wait_for_timeout(600); pg.screenshot(path='/tmp/s2.png'); out(L+'_slash','/tmp/s2.png',1100)
        print('ERRS',name,errs[:4]); print('BAD',name,bad[:12])
        ctx.close()
    b.close()

S1PY
cd /tmp
/workspace/nox/venv/bin/python /workspace/nox/tools/s1_shot.py chat.html fx3 busy vp=pc,mob 2>&1 | cut -c1-900
