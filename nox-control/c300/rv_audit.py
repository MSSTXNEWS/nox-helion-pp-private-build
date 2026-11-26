import sys,os,json,time
from playwright.sync_api import sync_playwright
AXE=open('/workspace/nox/tools/uiscore/node_modules/axe-core/axe.min.js').read()
BASE='http://127.0.0.1:18091/web/'
OUT='/workspace/nox/state/rv'; os.makedirs(OUT,exist_ok=True)
pages=sys.argv[1:]
JS_METRICS='''()=>{
 function deep(root,sel,acc){acc=acc||[];root.querySelectorAll(sel).forEach(e=>acc.push(e));root.querySelectorAll('*').forEach(e=>{if(e.shadowRoot)deep(e.shadowRoot,sel,acc)});return acc}
 function vis(e){var b=e.getBoundingClientRect(),s=getComputedStyle(e);return b.width>0&&b.height>0&&s.visibility!='hidden'&&s.display!='none'&&s.opacity!='0'&&b.bottom>0&&b.right>0&&b.left<innerWidth+5}
 function d(e){return e.tagName.toLowerCase()+(e.id?'#'+e.id:'')+(e.className&&typeof e.className=='string'?'.'+e.className.trim().split(/\\s+/).slice(0,2).join('.'):'')+' "'+((e.innerText||e.getAttribute('aria-label')||e.title||e.value||'')+'').trim().slice(0,20)+'"'}
 var sel=deep(document,'select,sl-select,[role=combobox],[role=listbox],datalist,input[list]').filter(vis).map(d).slice(0,10);
 var tg=deep(document,'button,a[href],input:not([type=hidden]),textarea,[role=button],[role=tab],sl-button,sl-icon-button,sl-tab,[onclick]').filter(vis).filter(e=>{var b=e.getBoundingClientRect();return b.width<43.5||b.height<43.5}).map(e=>{var b=e.getBoundingClientRect();return d(e)+' '+Math.round(b.width)+'x'+Math.round(b.height)});
 var ndoc=document.documentElement;
 return {txt:(document.body.innerText||'').trim().length,nvis:deep(document,'button,a[href],input,textarea').filter(vis).length,
  hscroll:ndoc.scrollWidth-innerWidth,sel:sel,small:tg.length,smallS:tg.slice(0,12),title:document.title,
  imgBroken:Array.from(document.images).filter(i=>i.complete&&i.naturalWidth==0&&i.src).map(i=>i.src.slice(-60)).slice(0,5)}}'''
JS_CLICKABLES='''()=>{function vis(e){var b=e.getBoundingClientRect(),s=getComputedStyle(e);return b.width>0&&b.height>0&&s.visibility!='hidden'&&s.display!='none'&&b.top<innerHeight&&b.bottom>0&&b.left<innerWidth&&b.right>0}
 var a=Array.from(document.querySelectorAll('button,[role=button],a,sl-button,sl-icon-button,[onclick]')).filter(vis).filter(e=>!e.disabled);
 a.forEach((e,i)=>e.setAttribute('data-rvi',i));return a.map((e,i)=>({i:i,t:e.tagName.toLowerCase()+' "'+((e.innerText||e.getAttribute('aria-label')||e.title||'')+'').trim().slice(0,24)+'"'+(e.id?' #'+e.id:''),href:e.getAttribute('href')||''}))}'''
def run():
  with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
    for name in pages:
      for w,h in ((390,844),(1440,900),(1920,1080)):
        res={'page':name,'w':w}
        try:
          mob=w<500
          c=b.new_context(viewport={'width':w,'height':h},has_touch=mob,is_mobile=mob)
          pg=c.new_page(); errs=[]
          pg.on('pageerror',lambda e:errs.append('PE '+str(e)[:140]))
          pg.on('console',lambda m:errs.append('CE '+m.text[:140]) if m.type=='error' and 'Failed to load resource' not in m.text else None)
          pg.on('response',lambda r:errs.append('HTTP%d %s'%(r.status,r.url.split('127.0.0.1:18091')[-1][:80])) if r.status>=400 else None)
          pg.on('requestfailed',lambda r:errs.append('RF '+r.url.split('127.0.0.1:18091')[-1][:80]) if '127.0.0.1' in r.url else None)
          pg.route('**/api/nox/outbox*',lambda r:r.fulfill(status=200,content_type='application/json',body='{"messages":[]}'))
          t0=time.time(); pg.goto(BASE+name,wait_until='load',timeout=40000); pg.wait_for_timeout(3500)
          res['load_s']=round(time.time()-t0,1)
          res.update(pg.evaluate(JS_METRICS))
          try:
            pg.add_script_tag(content=AXE)
            ax=pg.evaluate("axe.run(document,{runOnly:['color-contrast']}).then(r=>r.violations.map(v=>v.nodes.map(n=>n.target.join('>').slice(0,50)+' '+(n.any[0]&&n.any[0].data?(n.any[0].data.contrastRatio+'/'+n.any[0].data.expectedContrastRatio):''))).flat())")
            res['contrast']=len(ax); res['contrastS']=ax[:6]
          except Exception as e: res['contrast']=-1; res['axeErr']=str(e)[:80]
          pg.screenshot(path='%s/%s_%d.jpg'%(OUT,name.replace('.html',''),w),type='jpeg',quality=72)
          if w==1440:
            cl=pg.evaluate(JS_CLICKABLES); res['nclick']=len(cl); dead=[]
            for it in cl[:45]:
              if it['href'] and not it['href'].startswith(('#','javascript')):
                continue
              try:
                pg.evaluate("window.__rvm=0;window.__rvo&&window.__rvo.disconnect();window.__rvo=new MutationObserver(m=>window.__rvm+=m.length);window.__rvo.observe(document,{subtree:true,childList:true,attributes:true,characterData:true})")
              except Exception: pass
              nreq=[0]; pg.on('request',lambda r:nreq.__setitem__(0,nreq[0]+1))
              u0=pg.url; dlg=[0]; pg.once('dialog',lambda d:(dlg.__setitem__(0,1),d.dismiss()))
              try:
                pg.click('[data-rvi="%d"]'%it['i'],timeout=1500,force=True,no_wait_after=True); pg.wait_for_timeout(350)
                ch=pg.evaluate("window.__rvm||0") if pg.url==u0 else 99
                if pg.url==u0 and ch==0 and nreq[0]==0 and not dlg[0]: dead.append(it['t'])
              except Exception as e:
                dead.append(it['t']+' ERR '+str(e)[:40])
              if pg.url!=u0 or pg.evaluate("document.querySelectorAll('[data-rvi]').length")==0:
                pg.goto(BASE+name,wait_until='load'); pg.wait_for_timeout(1500); pg.evaluate(JS_CLICKABLES)
            res['dead']=dead[:15]; res['ndead']=len(dead)
            links=sorted({x['href'] for x in cl if x['href'] and not x['href'].startswith(('#','javascript','mailto','http'))})
            bad=[]
            for l in links[:40]:
              try:
                r=pg.request.get(pg.url.rsplit('/',1)[0]+'/'+l.lstrip('./') if not l.startswith('/') else 'http://127.0.0.1:18091'+l,timeout=8000)
                if r.status>=400: bad.append('%d %s'%(r.status,l))
              except Exception as e: bad.append('ERR '+l)
            res['badlinks']=bad
          res['errs']=errs[:10]; res['nerr']=len(errs)
          c.close()
        except Exception as e:
          res['fatal']=repr(e)[:160]
        print(json.dumps(res,ensure_ascii=False),flush=True)
    b.close()
run()
