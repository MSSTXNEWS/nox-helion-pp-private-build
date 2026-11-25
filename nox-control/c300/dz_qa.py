import asyncio,sys,json,base64,time
from playwright.async_api import async_playwright
URL='http://127.0.0.1:8091/web/creative.html'
async def main():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for tag,w,h,sc in (('pc',1440,900,1),('mob',390,844,1),('4k',3840,2160,1)):
      c=await b.new_context(viewport={'width':w,'height':h},device_scale_factor=sc);pg=await c.new_page();errs=[]
      pg.on('pageerror',lambda e:errs.append('PE '+str(e)[:160]))
      pg.on('console',lambda m:errs.append('CE '+m.text[:160]) if m.type=='error' else None)
      await pg.goto(URL,wait_until='load',timeout=30000);await pg.wait_for_timeout(3500)
      info=await pg.evaluate('''()=>{var r=[];document.querySelectorAll('#dz sl-button,#dz sl-icon-button,#dz sl-select,#dz sl-input,#dz sl-switch,#dz sl-color-picker,#dz sl-tab').forEach(e=>{var b=e.getBoundingClientRect();var vis=b.width>0&&b.height>0&&getComputedStyle(e).visibility!='hidden';var cs=e.closest('#dzSide:not(.open)');if(vis&&(b.height<43.5||b.width<43.5)&&!(innerWidth<=900&&cs))r.push(e.tagName.toLowerCase()+' '+(e.getAttribute('data-act')||e.getAttribute('data-tool')||e.id||e.getAttribute('name')||'')+' '+Math.round(b.width)+'x'+Math.round(b.height))});return{small:r.slice(0,40),n:r.length,cv:!!window.NOXDZ,tools:document.querySelectorAll('[data-tool]').length}}''')
      print('OUT:',tag,json.dumps(info,ensure_ascii=False)[:900])
      if tag=='pc':
        # прокликать все кнопки
        dead=await pg.evaluate('''async()=>{var bad=[];var A=NOXDZ.ACT,I=NOXDZ.AIACT;document.querySelectorAll('#dz [data-act]').forEach(b=>{var k=b.dataset.act;if(!(A[k]||I[k]))bad.push(k)});return bad}''')
        print('OUT: dead',dead)
        for k in ['rect','ellipse','line','arrow','poly','pen','brush','doodle','eraser','text','fill','pick','mask','lasso','zoom','hand','select']:
          await pg.click('[data-tool="%s"]'%k,force=True)
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
      await pg.screenshot(path='/tmp/dz_%s.jpg'%tag,type='jpeg',quality=38)
      print('OUT: errs',tag,len(errs),errs[:6])
      print('B64',tag,base64.b64encode(open('/tmp/dz_%s.jpg'%tag,'rb').read()).decode())
      await c.close()
    await b.close()
asyncio.run(main())
