import asyncio,sys,json,base64,time
from playwright.async_api import async_playwright
URL='http://127.0.0.1:8091/web/creative.html'
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for tag,w,h,sc in (('pc',1440,900,1),('mob',390,844,1),('4k',3840,2160,1)):
      c=await b.new_context(viewport={'width':w,'height':h},device_scale_factor=sc);pg=await c.new_page();errs=[]
      pg.on('pageerror',lambda e:errs.append('PE '+str(e)[:160]))
      pg.on('console',lambda m:errs.append('CE '+m.text[:160]) if m.type=='error' else None);pg.on('response',lambda r:errs.append('HTTP%d %s'%(r.status,r.url[-70:])) if r.status>=400 else None)
      await pg.goto(URL,wait_until='load',timeout=30000);await pg.wait_for_timeout(3500)
      info=await pg.evaluate('''()=>{var r=[];document.querySelectorAll('#dz sl-button,#dz sl-icon-button,#dz sl-select,#dz sl-input,#dz sl-switch,#dz sl-color-picker,#dz sl-tab').forEach(e=>{var b=e.getBoundingClientRect();var vis=b.width>0&&b.height>0&&getComputedStyle(e).visibility!='hidden';var cs=e.closest('#dzSide:not(.open)');if(vis&&(b.height<43.5||b.width<43.5)&&!(innerWidth<=900&&cs))r.push(e.tagName.toLowerCase()+' '+(e.getAttribute('data-act')||e.getAttribute('data-tool')||e.id||e.getAttribute('name')||'')+' '+Math.round(b.width)+'x'+Math.round(b.height))});return{small:r.slice(0,40),n:r.length,cv:!!window.NOXDZ,tools:document.querySelectorAll('[data-tool]').length}}''')
      for tb in ('lay','prop','ai'):
        await pg.evaluate("document.querySelector('sl-tab[panel=%s]').click()"%tb);await pg.wait_for_timeout(400)
        i2=await pg.evaluate('''()=>{var r=[];document.querySelectorAll('#dzSide sl-button,#dzSide sl-icon-button,#dzSide sl-select,#dzSide sl-input,#dzSide sl-switch,#dzSide sl-color-picker,#dzSide sl-tab,#dzSide sl-textarea').forEach(e=>{var b=e.getBoundingClientRect();if(b.width>0&&b.height>0&&(b.height<43.5||b.width<43.5)&&!e.closest('sl-tab-panel:not([active])'))r.push(e.tagName.toLowerCase()+' '+(e.getAttribute('data-act')||e.id||'')+' '+Math.round(b.width)+'x'+Math.round(b.height))});return r.slice(0,20)}''')
        print('OUT: small in',tb,tag,i2)
      print('OUT:',tag,json.dumps(info,ensure_ascii=False)[:900])
      if tag=='pc':
        # прокликать все кнопки
        dead=await pg.evaluate('''async()=>{var bad=[];var A=NOXDZ.ACT,I=NOXDZ.AIACT;document.querySelectorAll('#dz [data-act]').forEach(b=>{var k=b.dataset.act;if(!(A[k]||I[k]))bad.push(k)});return bad}''')
        print('OUT: dead',dead)
        for k in ['rect','ellipse','line','arrow','poly','pen','brush','doodle','eraser','text','fill','pick','mask','lasso','zoom','hand','select']:
          await pg.click('[data-tool="%s"]'%k,force=True)
        # тест маски: оригинал вне маски не меняется
        await pg.evaluate("""()=>{window.__fx=fetch;window.fetch=function(u,o){if(String(u).indexOf('/vision/describe')>=0)return Promise.resolve(new Response(JSON.stringify({text:'<svg viewBox=\\"0 0 100 100\\"><g id=\\"t\\"><rect id=\\"big\\" x=\\"0\\" y=\\"0\\" width=\\"100\\" height=\\"100\\" fill=\\"#00ff00\\"/><text id=\\"cap\\" x=\\"10\\" y=\\"50\\" font-size=\\"20\\" fill=\\"#000\\">Hi</text></g></svg>'}),{status:200,headers:{'Content-Type':'application/json'}}));return window.__fx.apply(this,arguments)}}""")
        await pg.evaluate("""()=>{var cv=NOXDZ.cv;cv.getObjects().filter(o=>!o.dzArt).forEach(o=>cv.remove(o));var r=new fabric.Rect({left:0,top:0,width:400,height:400,fill:'#ff0000'});cv.add(r);NOXDZ.setTool('mask')}""")
        box=await pg.evaluate("(()=>{var r=document.querySelector('#dzStage').getBoundingClientRect();return[r.x,r.y,r.width,r.height]})()")
        pz=await pg.evaluate("(()=>{var cv=NOXDZ.cv,vt=cv.viewportTransform;return [vt[0],vt[4],vt[5]]})()")
        def sx(x):return box[0]+pz[1]+x*pz[0]
        def sy(y):return box[1]+pz[2]+y*pz[0]
        await pg.mouse.move(sx(100),sy(100));await pg.mouse.down();await pg.mouse.move(sx(200),sy(100),steps=8);await pg.mouse.move(sx(200),sy(200),steps=8);await pg.mouse.up()
        await pg.evaluate("document.querySelector('sl-tab[panel=ai]').click()")
        await pg.evaluate("NOXDZ.run('sketch')")
        await pg.wait_for_selector('sl-dialog[open] [data-y]',timeout=8000);await pg.click('sl-dialog[open] [data-y]',force=True);await pg.wait_for_timeout(1500)
        res=await pg.evaluate("""()=>{var cv=NOXDZ.cv;var L=cv.getObjects().filter(o=>/^ИИ/.test(o.name||''));var tb=L.filter(o=>o.type==='textbox').length;var cp=L.filter(o=>o.clipPath).length;var u=cv.toDataURL({left:300,top:300,width:2,height:2,format:'png',multiplier:1});return new Promise(function(res){var im=new Image();im.onload=function(){var c=document.createElement('canvas');c.width=c.height=2;var x=c.getContext('2d');x.drawImage(im,0,0);res({layers:L.length,textbox:tb,clipped:cp,px:Array.from(x.getImageData(0,0,1,1).data)})};im.src=u})}""")
        print('OUT: MASKTEST',res,'(ожидаем clipped>0, textbox>=1, px вне маски 255,0,0)')
        await pg.reload();await pg.wait_for_timeout(2500)
        await pg.evaluate("localStorage.clear()");await pg.reload();await pg.wait_for_timeout(2500)
        # нарисовать домик каракулями
        await pg.click('[data-tool="doodle"]',force=True)
        box=await pg.evaluate("(()=>{var r=document.querySelector('#dzStage').getBoundingClientRect();return[r.x,r.y,r.width,r.height]})()")
        x0,y0=box[0]+box[2]/2-150,box[1]+box[3]/2-80
        async def stroke(pts):
          await pg.mouse.move(x0+pts[0][0],y0+pts[0][1]);await pg.mouse.down()
          for q in pts[1:]:await pg.mouse.move(x0+q[0],y0+q[1],steps=6)
          await pg.mouse.up()
        await stroke([(0,100),(0,220),(200,220),(200,100),(0,100)])
        await stroke([(-20,100),(100,0),(220,100),(-20,100)])
        await stroke([(80,220),(80,150),(120,150),(120,220)])
        await stroke([(20,120),(20,160),(55,160),(55,120),(20,120)])
        await pg.click('[data-tool="select"]',force=True)
        await pg.wait_for_timeout(800)
        n=await pg.evaluate('NOXDZ.cv.getObjects().length');print('OUT: objects after doodle',n)
        await pg.evaluate("document.querySelector('sl-tab[panel=ai]').click()");await pg.wait_for_timeout(500)
        # ctrl+a выделение всё
        await pg.evaluate("(()=>{var cv=NOXDZ.cv;var o=cv.getObjects().filter(x=>!x.dzArt);var s=new fabric.ActiveSelection(o,{canvas:cv});cv.setActiveObject(s);cv.requestRenderAll()})()")
        await pg.click('[data-act="ai-sketch"]',force=True)
        await pg.wait_for_selector('sl-dialog[open] [data-y]',timeout=8000)
        await pg.screenshot(path='/tmp/dz_plan.jpg',type='jpeg',quality=38)
        t0=time.time();await pg.click('sl-dialog[open] [data-y]',force=True)
        for i in range(60):
          await pg.wait_for_timeout(5000)
          cnt=await pg.evaluate('NOXDZ.cv.getObjects().filter(o=>/^ИИ/.test(o.name||"")).length')
          if cnt>0: break
          st=await pg.evaluate("document.getElementById('dzAIOut').textContent")
          if st.startswith('Ошибка'): break
        print('OUT: sketch2svg layers',cnt,round(time.time()-t0),'s',(await pg.evaluate("document.getElementById('dzAIOut').textContent"))[:200])
        names=await pg.evaluate('NOXDZ.cv.getObjects().filter(o=>/^ИИ/.test(o.name||"")).map(o=>o.name+":"+o.type)')
        print('OUT: layers',names)
      await pg.screenshot(path='/tmp/dz_%s.jpg'%tag,type='jpeg',quality=30)
      errs=[e for e in errs if 'img/generate' not in e and 'Failed to load resource' not in e and 'three' not in e];print('OUT: errs',tag,len(errs),errs[:6])
      if tag!='4k': print('B64',tag,base64.b64encode(open('/tmp/dz_%s.jpg'%tag,'rb').read()).decode())
      await c.close()
    await b.close()
asyncio.run(main());print('OUT_END')
