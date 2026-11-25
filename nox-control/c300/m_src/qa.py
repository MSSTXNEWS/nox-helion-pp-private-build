import asyncio,json,base64,sys,os
from playwright.async_api import async_playwright
nav=json.load(open('/workspace/nox/web/site/nav.json'))
pages=['index']+[i['file'][:-5] for g in nav['groups'] for i in g['items']]
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
                    await c.wait_for_timeout(3500)
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
