from playwright.sync_api import sync_playwright
U='http://127.0.0.1:8091/web/'
with sync_playwright() as p:
    b=p.chromium.launch();pg=b.new_page(viewport={'width':1920,'height':1080})
    pg.route('**/api/nox/outbox*',lambda r:r.fulfill(status=200,content_type='application/json',body='{"messages":[]}'))
    errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:200]));pg.on('console',lambda c:errs.append(c.text[:120]) if c.type=='error' else None)
    pg.goto(U+'chat-dc.html',wait_until='load');pg.evaluate("localStorage.setItem('nox.wow.cur','qa-dct2')");pg.reload();pg.wait_for_timeout(3000)
    pg.evaluate("document.querySelector('deep-chat').submitUserMessage({text:'Назови столицу Франции'})")
    for i in range(100):
        if pg.evaluate("!!document.querySelector('deep-chat').shadowRoot.querySelector('.dc-acts-live')"):break
        pg.wait_for_timeout(1000)
    print('acts',pg.evaluate("[...document.querySelector('deep-chat').shadowRoot.querySelectorAll('.dc-acts-live button')].map(b=>b.title)"))
    print('click',pg.evaluate("(()=>{const b=[...document.querySelector('deep-chat').shadowRoot.querySelectorAll('.dc-acts-live button')].find(b=>b.title==='Ответить на это сообщение');if(!b)return 'nobtn';b.click();return 'ok'})()"))
    pg.wait_for_timeout(600)
    print('reply',pg.evaluate("(document.querySelector('deep-chat').shadowRoot.querySelector('.dc-reply')||{}).innerText"),errs[:3])
    pg.evaluate("document.querySelector('deep-chat').submitUserMessage({text:'а население?'})");pg.wait_for_timeout(4000)
    print('sent',pg.evaluate("window.NOXdc.cur().msgs.filter(m=>m.role==='user').map(m=>m.content.slice(0,80))"),errs[:2])
    b.close()
