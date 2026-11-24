p='/workspace/nox/qa_audit.py'; s=open(p,encoding='utf-8').read()
import shutil,os
if not os.path.exists(p+'.bak_w3_1'): shutil.copy(p,p+'.bak_w3_1')
a='            await pg.keyboard.press("Escape")\n            shots[vp]='
b='''            await pg.keyboard.press("Escape")
            if page=="chat.html":  # W3: пустой чат не показывает ленту/оценки/«думает» -> реальное тестовое сообщение
                try:
                    await pg.fill("#input","Напиши python-функцию сложения двух чисел в блоке кода и одним предложением объясни.")
                    await pg.press("#input","Enter"); await pg.wait_for_timeout(3000)
                    shots["think_"+vp]=await pg.screenshot(type="jpeg",quality=60)
                    for _ in range(60):
                        await pg.wait_for_timeout(2000)
                        if await pg.evaluate("document.querySelector('#btnStop').hidden && document.querySelectorAll('#msgs .m.a .txt').length>0 && document.querySelector('#msgs .m.a:last-child .txt').innerText.length>10"): break
                    await pg.wait_for_timeout(1500)
                except Exception: pass
            shots[vp]='''
if 'W3: пустой чат' not in s:
    assert a in s; s=s.replace(a,b,1); open(p,'w',encoding='utf-8').write(s); print('qa_audit patched')
m='/workspace/nox/web/site/nox-manual.js'; t=open(m,encoding='utf-8').read()
if not os.path.exists(m+'.bak_w3_1'): shutil.copy(m,m+'.bak_w3_1')
if 'W3PILL' not in t:
    t=t.replace("pill.id = 'nxmPill';","pill.id = 'nxmPill'; pill.title = 'Справка старшего'; pill.setAttribute('aria-label','Справка старшего'); if(!document.getElementById('w3pill')){document.head.insertAdjacentHTML('beforeend','<style id=\"w3pill\">/*W3PILL*/#nxmPill{left:8px!important;right:auto!important;top:auto!important;bottom:124px!important;width:44px!important;height:44px!important;min-width:44px!important;padding:0!important;font-size:0!important;border-radius:50%!important;opacity:.75;display:flex;align-items:center;justify-content:center}#nxmPill::before{content:\"?\";font-size:18px;color:#f3e9e4}#nxmPill:hover{opacity:1}</style>');}",1)
    open(m,'w',encoding='utf-8').write(t); print('pill patched')
