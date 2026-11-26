echo "C300: w_s4"
N=/workspace/nox; export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/s4.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox']);pg=b.new_page();reqs=[]
    pg.on('request',lambda r:reqs.append(r.url.split('18091')[-1][:40]) if any(k in r.url for k in ('/img/','api/chat','api/turn')) else None)
    pg.goto('http://127.0.0.1:18091/web/chat-dc.html',wait_until='load');pg.evaluate("localStorage.setItem('nox.wow.cur','qa-draw-s4')");pg.reload();pg.wait_for_timeout(4000)
    print(pg.evaluate("""()=>{const dc=document.querySelector('deep-chat');const h=dc.connect.handler;window.__log=[];
      const sg={onOpen(){__log.push('open')},onResponse(r){__log.push('resp:'+JSON.stringify(r).slice(0,60))},onClose(){__log.push('close')},stopClicked:{}};
      try{h({messages:[{role:'user',text:'нарисуй простой красный круг'}],files:[]},sg)}catch(e){__log.push('ERR '+e.message)};return h.toString().slice(0,140)}"""))
    pg.wait_for_timeout(6000);print(pg.evaluate("window.__log"),reqs);b.close()
P
timeout 60 $N/venv/bin/python /tmp/s4.py 2>&1 | cut -c1-500
