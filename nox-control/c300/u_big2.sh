echo "C300: u_big2"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
echo "== 1 draw.js: показ ошибки генерации"
cp nox-k8-draw.js nox-k8-draw.js.bak_u2_$TS
python3 - <<'PYX'
f='nox-k8-draw.js';s=open(f,encoding='utf-8').read()
o="let u=findImg(j);if(u)return u;"
if 'Генерация недоступна' not in s and o in s:
    s=s.replace(o,o+"if(j&&j.error&&window.K8studio)K8studio.post({t:'Генерация недоступна: '+(j.reason||j.error),ts:Date.now()});",1);open(f,'w',encoding='utf-8').write(s);print('patched')
PYX
node --check nox-k8-draw.js && echo SYNTAX_OK || cp nox-k8-draw.js.bak_u2_$TS nox-k8-draw.js
sed -i 's#nox-k8-draw.js?v=u1#nox-k8-draw.js?v=u2#' creative.html
echo "== 2 мобильный fix: периодический проход"
cp nox-m-mobile.js nox-m-mobile.js.bak_u_$TS
python3 - <<'PYX'
f='nox-m-mobile.js';s=open(f,encoding='utf-8').read()
o="window.__noxMfix = fix;"
if 'U_FIXLOOP' not in s and o in s:
    s=s.replace(o,o+" /* U_FIXLOOP */ setInterval(()=>{ if(mq.matches) fix(); },1500); try{ new MutationObserver(()=>{ clearTimeout(window.__uT); window.__uT=setTimeout(fix,150); }).observe(document.documentElement,{attributes:true,subtree:true,attributeFilter:['class','style','hidden','open']}); }catch(e){}",1);open(f,'w',encoding='utf-8').write(s);print('patched')
PYX
node --check nox-m-mobile.js && echo SYNTAX_OK || { cp nox-m-mobile.js.bak_u_$TS nox-m-mobile.js; echo ROLLBACK; }
tar czf /tmp/u_pages_$TS.tgz *.html 2>/dev/null; sed -i -E 's#nox-m-mobile\.js\?v=[A-Za-z0-9_]+#nox-m-mobile.js?v=u1#' *.html; grep -l "nox-m-mobile.js?v=u1" *.html | wc -l
echo "U: мобильный fix: периодический проход" >> qa/rework/chat.fixed
echo "== 3 background: mobile QA, audit, minichat, 4K"
cat > /tmp/u_mqa.py <<'MEOF'
import asyncio,json,base64,sys,os
from playwright.async_api import async_playwright
nav=json.load(open('/workspace/nox/web/site/nav.json'))
pages=['index']+[i['file'][:-5] for g in nav['groups'] for i in g['items']]
if os.environ.get('PAGES'): pages=os.environ['PAGES'].split(',')
W=[int(x) for x in os.environ.get('WIDTHS','390').split(',')]
SHOT=os.environ.get('SHOTS','').split(',')
JS="""()=>{const w=innerWidth,r={};const tab=document.querySelector('#nox-m-tab');r.tab=!!tab;
const tb=tab?tab.getBoundingClientRect():null;
r.sw=document.documentElement.scrollWidth;
const q='a,button,[role=button],[role=tab],input:not([type=hidden]),select,summary,sl-button,sl-icon-button,sl-tab';
r.small=[];document.querySelectorAll(q).forEach(e=>{if(e.closest('#nxdock'))return;const b=e.getBoundingClientRect();const s=getComputedStyle(e);if(!b.width||!b.height||s.visibility==='hidden'||s.opacity==='0'||b.left<-50||b.top>innerHeight*3)return;if(e.offsetParent===null&&s.position!=='fixed')return;if(b.width<43.5||b.height<43.5)r.small.push((e.tagName+'#'+e.id+'.'+(typeof e.className==='string'?e.className.split(' ')[0]:'')+' '+Math.round(b.width)+'x'+Math.round(b.height)+' '+(e.innerText||'').slice(0,12).replace(/\\n/g,' ')))});
r.font=0;const wk=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;const seen=new Set();r.fontEx=[];while((n=wk.nextNode())){if(!n.nodeValue.trim())continue;const e=n.parentElement;if(!e||seen.has(e)||e.closest('script,style,svg,canvas,#nxdock'))continue;seen.add(e);const b=e.getBoundingClientRect();if(!b.width||!b.height||getComputedStyle(e).visibility==='hidden')continue;const fz=parseFloat(getComputedStyle(e).fontSize);if(fz>=1&&fz<13.9){r.font++;if(r.fontEx.length<2)r.fontEx.push(e.tagName+'.'+(typeof e.className==='string'?e.className.split(' ')[0]:'')+getComputedStyle(e).fontSize)}}
r.wide=[];document.querySelectorAll('body *').forEach(e=>{if(e.closest('#nxdock'))return;const b=e.getBoundingClientRect();const s=getComputedStyle(e);if(s.position==='fixed'||!b.width||s.visibility==='hidden')return;if(b.right>w+2&&b.left>=-2){let p=e.parentElement,sc=false;while(p&&p!==document.body){const o=getComputedStyle(p).overflowX;if((o==='auto'||o==='scroll'||o==='hidden')&&p.getBoundingClientRect().right<=w+2){sc=true;break}p=p.parentElement}if(!sc&&r.wide.length<4)r.wide.push(e.tagName+'#'+e.id+'.'+(typeof e.className==='string'?e.className.split(' ')[0]:'')+' r'+Math.round(b.right))}});
r.ovl=[];if(tb){document.querySelectorAll('body *').forEach(e=>{if(e.closest('#nox-m-tab,#nox-m-ai,.nox-m-sheet,#nox-m-scrim'))return;const s=getComputedStyle(e);if(s.position!=='fixed'||s.opacity==='0'||s.pointerEvents==='none')return;const b=e.getBoundingClientRect();if(b.width>300&&b.height>600)return;if(b.width<2)return;if(b.bottom>tb.top+2&&b.top<tb.bottom&&b.right>0&&b.left<w)r.ovl.push(e.tagName+'#'+e.id+'.'+(typeof e.className==='string'?e.className.split(' ')[0]:''))});
const sun=document.querySelector('#nxsun');if(sun){const b=sun.getBoundingClientRect();r.sunY=Math.round(b.bottom)}}
return r}"""
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for w in W:
            for pg in pages:
                c=await b.new_page(viewport={"width":w,"height":844 if w<500 else 1024})
                errs=[]
                c.on('pageerror',lambda e:errs.append(str(e)[:100]))
                try:
                    for t in range(3):
                        try: await c.goto("http://127.0.0.1:8091/web/%s.html"%pg,wait_until="load",timeout=25000);break
                        except Exception as e:
                            if t==2: raise
                            await asyncio.sleep(3)
                    await c.wait_for_timeout(int(os.environ.get('WAIT','3500')))
                    r=await c.evaluate(JS)
                    bad=len(errs)+(1 if r['sw']>w else 0)+len(r['small'])+len(r['ovl'])+len(r['wide'])
                    print("OUT: %d %-14s js%d sw%d tab%d small%d font%d wide%d ovl%d %s"%(w,pg,len(errs),r['sw'],r['tab'],len(r['small']),r['font'],len(r['wide']),len(r['ovl']),"OK" if not bad and not r['font'] else "!!"))
                    if bad or r['font']:
                        print("OUT:    ",errs[:2],r['small'][:5],r['wide'][:3],r['ovl'][:3],r['fontEx'])
                    if pg in SHOT:
                        await c.screenshot(path="/tmp/m_%s_%d.jpg"%(pg,w),type="jpeg",quality=38)
                        print("B64_%s%d_BEGIN"%(pg,w));print(base64.b64encode(open("/tmp/m_%s_%d.jpg"%(pg,w),'rb').read()).decode());print("B64_%s%d_END"%(pg,w))
                        if os.environ.get('SHEET'):
                            for tag,sel in (('more','#nox-m-more'),('cmd','a[href="#cmd"]')):
                                if await c.query_selector(sel):
                                    await c.click(sel);await c.wait_for_timeout(900)
                                    await c.screenshot(path="/tmp/m_s.jpg",type="jpeg",quality=38)
                                    print("B64_%s%s%d_BEGIN"%(pg,tag,w));print(base64.b64encode(open("/tmp/m_s.jpg",'rb').read()).decode());print("B64_%s%s%d_END"%(pg,tag,w))
                                    await c.keyboard.press('Escape');await c.mouse.click(200,60);await c.wait_for_timeout(400)
                except Exception as e: print("OUT: %d %s FAIL %s"%(w,pg,str(e)[:100]))
                await c.close()
        await b.close()
asyncio.run(main())
MEOF
cp /tmp/u_audit.py /tmp/u_audit_bak.py 2>/dev/null
cat > /tmp/u_audit.py <<'AEOF'
import asyncio,json,sys,os
from playwright.async_api import async_playwright
nav=json.load(open('/workspace/nox/web/site/nav.json'))
pages=['index']+[i['file'][:-5] for g in nav['groups'] for i in g['items']]
if os.environ.get('PAGES'): pages=os.environ['PAGES'].split(',')
MODE=os.environ.get('MODE','audit')
SEL="button,[role=button],sl-button,sl-icon-button,summary,a[href^='#'],a[href='']"
COLLECT="""()=>{const out=[];document.querySelectorAll("%s").forEach((e,i)=>{if(e.closest('#nxdock,#nox-m-tab,#nox-m-ai'))return;const b=e.getBoundingClientRect(),s=getComputedStyle(e);if(b.width<4||b.height<4||s.visibility==='hidden'||s.display==='none'||b.top<0||b.top>innerHeight||b.left<0||b.left>innerWidth||e.disabled)return;e.setAttribute('data-u-i',String(out.length));out.push((e.id||e.className&&String(e.className).split(' ')[0]||e.tagName)+'|'+(e.innerText||e.getAttribute('aria-label')||e.title||'').trim().slice(0,20))});return out.slice(0,30)}"""%SEL
SIG="()=>[location.href,document.body.innerText.length,document.querySelectorAll('[open],.open,.show,[class*=active]').length,document.body.querySelectorAll('*').length].join('/')"
async def audit(b):
  for pg in pages:
    c=await b.new_page(viewport={'width':1440,'height':900});errs=[];reqs=[0]
    c.on('pageerror',lambda e:errs.append(str(e)[:80]));c.on('request',lambda r:reqs.__setitem__(0,reqs[0]+1) if r.method!='GET' or '/api/' in r.url or '/svc/' in r.url else None)
    try:
      await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded',timeout=30000);await c.wait_for_timeout(2500)
      names=await c.evaluate(COLLECT);dead=[];r0=reqs[0]
      for i,n in enumerate(names):
        try:
          s1=await c.evaluate(SIG);rq=reqs[0]
          await c.click('[data-u-i="%d"]'%i,timeout=1500,no_wait_after=True);await c.wait_for_timeout(300)
          s2=await c.evaluate(SIG)
          if s1==s2 and reqs[0]==rq: dead.append(n)
          if not s2.startswith(c.url.split('#')[0][:20]) or s2.split('/')[0]!=s1.split('/')[0]:
            await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded');await c.wait_for_timeout(1500);await c.evaluate(COLLECT)
          await c.keyboard.press('Escape')
        except Exception as e: pass
      print('AUD %-14s btn%d dead%d req%d js%d %s %s'%(pg,len(names),len(dead),reqs[0]-r0,len(errs),dead[:8],errs[:2]),flush=True)
    except Exception as e: print('AUD EXC',pg,str(e)[:100],flush=True)
    await c.close()
async def mini(b):
  for pg in os.environ.get('PAGES','finance,news,music,calendar,mail,projects').split(','):
    c=await b.new_page(viewport={'width':1440,'height':900});errs=[]
    c.on('pageerror',lambda e:errs.append(str(e)[:80]))
    await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded');await c.wait_for_timeout(3000)
    info=await c.evaluate("""()=>{const f=document.querySelector('.nmc-fab,#nmcFab,#nxmPill,[id*=minichat],[class*=minichat],[class*=nmc]');return f?(f.id+'.'+String(f.className).slice(0,30)):null}""")
    r={'fab':info}
    if info:
      before=await c.evaluate("()=>document.querySelectorAll('*').length")
      try:
        await c.click('.nmc-fab,#nmcFab,#nxmPill',timeout=2000);await c.wait_for_timeout(1000)
        r['opened']=await c.evaluate("""()=>{const t=[...document.querySelectorAll('textarea,input[type=text],input:not([type])')].filter(x=>x.offsetParent&&x.closest('[class*=nmc],[id*=nmc],[class*=mini],[id*=mini]')).length;const ctx=(document.body.innerText.match(/контекст|страниц/i)||[''])[0];const bt=[...document.querySelectorAll('button')].filter(x=>x.offsetParent&&/Ответить|ghost|Tab/i.test(x.innerText)).length;return {inputs:t,ctx:ctx,reply:bt,ghost:typeof window.NOXGhost}}""")
      except Exception as e: r['err']=str(e)[:80]
    print('MINI',pg,json.dumps(r,ensure_ascii=False),errs[:2],flush=True)
    await c.close()
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    await (mini if MODE=='mini' else audit)(b)
    await b.close()
asyncio.run(main())
AEOF
nohup bash -c "cd $S; PAGES=chat,assistant,widgets,training,index,system WIDTHS=430,768 WAIT=5000 $PY /tmp/u_mqa.py > /tmp/u_mqa2.out 2>&1; MODE=mini $PY /tmp/u_audit.py > /tmp/u_mini.out 2>&1; $PY /tmp/u_audit.py > /tmp/u_aud.out 2>&1; echo FIN >> /tmp/u_aud.out" >/dev/null 2>&1 &
echo "bg started; u_big2 done"
