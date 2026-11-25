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
        pg.screenshot(path='/tmp/s.png')
        out(L+'_'+name,'/tmp/s.png',1100 if w>1500 else w)
        if 'slash' in opts and name=='pc':
            pg.fill('#input','/'); pg.wait_for_timeout(600); pg.screenshot(path='/tmp/s2.png'); out(L+'_slash','/tmp/s2.png',1100)
        print('ERRS',name,errs[:4]); print('BAD',name,bad[:12])
        ctx.close()
    b.close()

S1PY
S=/workspace/nox/web/site
cd $S
[ -f nox-home-v.css ] && cp -p nox-home-v.css nox-home-v.css.bak_s1_$(date +%H%M%S)
base64 -d > nox-home-v.css <<'S1EOF'
LyogTk9YIMK3INCT0LvQsNCy0L3QsNGPINCyINGA0LDRgdC60LvQsNC00LrQtSB2aXNpb25PUyBIb21lICsgUmF5Y2FzdC9MaW5lYXIgZGFzaGJvYXJkOiDQv9GA0LjQstC10YLRgdGC0LLQuNC1LCDQutGA0YPQv9C90YvQuSDQt9Cw0L/RgNC+0YEsINC/0LvQuNGC
0LrQuCDQtNC10LnRgdGC0LLQuNC5LCDQttC40LLRi9C1INC60LDRgNGC0L7Rh9C60LgsINGB0L7QsdGL0YLQuNGPLiDQotC+0LvRjNC60L4g0YHRgtC40LvQuCDQv9C+0LLQtdGA0YUgbm94LWhvbWUteC5jc3MuICovCmJvZHlbZGF0YS1wYWdlPWhvbWVdey0taHYt
cjoyMHB4Oy0taHYtZzpyZ2JhKDE4LDEyLDEyLC40Nik7LS1odi1iOnJnYmEoMjU1LDE2MCwxMjAsLjE2KX0KQG1lZGlhIChtaW4td2lkdGg6MjIwMHB4KXtib2R5W2RhdGEtcGFnZT1ob21lXSAucGFnZXt6b29tOjEuNX19CkBtZWRpYSAobWluLXdpZHRoOjMwMDBw
eCl7Ym9keVtkYXRhLXBhZ2U9aG9tZV0gLnBhZ2V7em9vbToyfX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLndyYXB7d2lkdGg6bWluKDExODBweCxjYWxjKDEwMCUgLSA0MHB4KSk7Z2FwOjE0cHh9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5waHtwYWRkaW5nOjA7bWFy
Z2luOjB9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5waD5kaXY6Zmlyc3QtY2hpbGR7ZGlzcGxheTpub25lfQpib2R5W2RhdGEtcGFnZT1ob21lXSAucGh7anVzdGlmeS1jb250ZW50OmZsZXgtZW5kO21hcmdpbi1ib3R0b206LTZweDtwb3NpdGlvbjpyZWxhdGl2ZTt6
LWluZGV4OjJ9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5waCAuYWN0cyAudGFne2Rpc3BsYXk6bm9uZX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLnBoIC5zZWd7YmFja2dyb3VuZDpub25lO2JvcmRlcjowO2JveC1zaGFkb3c6bm9uZTstd2Via2l0LWJhY2tkcm9wLWZp
bHRlcjpub25lO2JhY2tkcm9wLWZpbHRlcjpub25lfQpib2R5W2RhdGEtcGFnZT1ob21lXSAjcmVmcmVzaHttaW4taGVpZ2h0OjM0cHg7cGFkZGluZzowIDE0cHg7Ym9yZGVyLXJhZGl1czoxN3B4O2JvcmRlcjoxcHggc29saWQgdmFyKC0taHYtYik7YmFja2dyb3Vu
ZDpyZ2JhKDI1NSwxNDAsMTAwLC4wNyk7Zm9udC1zaXplOjEwLjVweDtsZXR0ZXItc3BhY2luZzouMTRlbTtjb2xvcjp2YXIoLS1tdSwjYzJhOWEwKX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gI3JlZnJlc2g6OmJlZm9yZSxib2R5W2RhdGEtcGFnZT1ob21lXSAjcmVm
cmVzaDo6YWZ0ZXJ7ZGlzcGxheTpub25lfQovKiDQvtCx0YnQtdC1INGB0YLQtdC60LvQviDQutCw0YDRgtC+0YfQtdC6ICovCmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5jYXJkLGJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1nbGFzc3tib3JkZXItcmFkaXVzOnZhcigt
LWh2LXIpO2JhY2tncm91bmQ6dmFyKC0taHYtZyk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1odi1iKTstd2Via2l0LWJhY2tkcm9wLWZpbHRlcjpibHVyKDI2cHgpIHNhdHVyYXRlKDEuMzUpO2JhY2tkcm9wLWZpbHRlcjpibHVyKDI2cHgpIHNhdHVyYXRlKDEuMzUp
O2JveC1zaGFkb3c6aW5zZXQgMCAxcHggMCByZ2JhKDI1NSwyNTUsMjU1LC4wNyksMCAxOHB4IDUwcHggcmdiYSgwLDAsMCwuMzUpfQpib2R5W2RhdGEtcGFnZT1ob21lXSAuY2FyZDo6YmVmb3JlLGJvZHlbZGF0YS1wYWdlPWhvbWVdIC5jYXJkOjphZnRlcntkaXNw
bGF5Om5vbmV9Ci8qINC/0YDQuNCy0LXRgtGB0YLQstC40LUgKyDRgdGC0YDQvtC60LAg0LfQsNC/0YDQvtGB0LAgKi8KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LWhlcm97Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOm1pbm1heCgwLDEuNmZyKSBtaW5tYXgoMCwxZnIp
O2dhcDoxNHB4O21hcmdpbjowfQpib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtaGl7cGFkZGluZzoyNnB4IDI4cHggMjJweDtkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rpb246Y29sdW1uO2p1c3RpZnktY29udGVudDpjZW50ZXJ9CmJvZHlbZGF0YS1wYWdlPWhvbWVd
IC5oeC1raWNre2ZvbnQtc2l6ZToxMHB4O2xldHRlci1zcGFjaW5nOi4zMmVtO29wYWNpdHk6Ljh9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1oe21hcmdpbjo4cHggMCA2cHg7Zm9udDozMDAgY2xhbXAoMjhweCwzLjR2dyw0NHB4KS8xLjA4IHZhcigtLWhlYWQs
aW5oZXJpdCk7bGV0dGVyLXNwYWNpbmc6LjE0ZW19CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1zdWJ7bWFyZ2luOjAgMCAyMHB4O2ZvbnQtc2l6ZToxNHB4O2NvbG9yOiNkOWMyYjZ9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1hc2t7cG9zaXRpb246cmVsYXRp
dmU7Z2FwOjA7ZmxleC13cmFwOm5vd3JhcDthbGlnbi1pdGVtczpjZW50ZXI7bWluLWhlaWdodDo2MnB4O3BhZGRpbmc6NnB4IDZweCA2cHggNTRweDtib3JkZXItcmFkaXVzOjIwcHg7YmFja2dyb3VuZDpyZ2JhKDgsNSw1LC41NSk7Ym9yZGVyOjFweCBzb2xpZCBy
Z2JhKDI1NSwxNjAsMTIwLC4yOCk7Ym94LXNoYWRvdzppbnNldCAwIDFweCAwIHJnYmEoMjU1LDI1NSwyNTUsLjA2KSwwIDEwcHggMzRweCByZ2JhKDAsMCwwLC4zNSk7dHJhbnNpdGlvbjpib3JkZXItY29sb3IgLjE1cyxib3gtc2hhZG93IC4xNXN9CmJvZHlbZGF0
YS1wYWdlPWhvbWVdIC5oeC1hc2s6Zm9jdXMtd2l0aGlue2JvcmRlci1jb2xvcjpyZ2JhKHZhcigtLWN5KSwuNyk7Ym94LXNoYWRvdzowIDAgMCAzcHggcmdiYSh2YXIoLS1jeSksLjE0KSwwIDEwcHggMzRweCByZ2JhKDAsMCwwLC4zNSl9CmJvZHlbZGF0YS1wYWdl
PWhvbWVdIC5oeC1hc2s6OmJlZm9yZXtjb250ZW50OicnO3Bvc2l0aW9uOmFic29sdXRlO2xlZnQ6MjBweDt0b3A6NTAlO3dpZHRoOjE1cHg7aGVpZ2h0OjE1cHg7bWFyZ2luLXRvcDotOXB4O2JvcmRlcjoycHggc29saWQgdmFyKC0tbXUsI2MyYTlhMCk7Ym9yZGVy
LXJhZGl1czo1MCV9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1hc2s6OmFmdGVye2NvbnRlbnQ6Jyc7cG9zaXRpb246YWJzb2x1dGU7bGVmdDozM3B4O3RvcDo1MCU7d2lkdGg6N3B4O2hlaWdodDoycHg7bWFyZ2luLXRvcDo2cHg7YmFja2dyb3VuZDp2YXIoLS1t
dSwjYzJhOWEwKTt0cmFuc2Zvcm06cm90YXRlKDQ1ZGVnKTtib3JkZXItcmFkaXVzOjFweH0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LWFzayBpbnB1dHtmbGV4OjEgMSBhdXRvO21pbi13aWR0aDowO21pbi1oZWlnaHQ6NDhweDtwYWRkaW5nOjAgOHB4O2JvcmRl
cjowO2JhY2tncm91bmQ6bm9uZTtmb250OjQwMCAxOHB4IHZhcigtLWJvZHksaW5oZXJpdCk7Y29sb3I6I2ZmZn0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LWFzayBpbnB1dDo6cGxhY2Vob2xkZXJ7Y29sb3I6dmFyKC0tbXUyLCM5YzgyNzkpfQpib2R5W2RhdGEt
cGFnZT1ob21lXSAuaHgtYXNrIGJ1dHRvbnttaW4taGVpZ2h0OjQ2cHg7cGFkZGluZzowIDIwcHg7Ym9yZGVyLXJhZGl1czoxNXB4O21hcmdpbi1sZWZ0OjZweDtmb250OjYwMCAxMnB4LzEgdmFyKC0tYm9keSxpbmhlcml0KTtsZXR0ZXItc3BhY2luZzouMDZlbTt0
ZXh0LXRyYW5zZm9ybTpub25lO2NvbG9yOiNmZmYzZWE7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoMTYwZGVnLHJnYih2YXIoLS1hbSkpLHJnYih2YXIoLS1jeSkpKTtib3JkZXI6MDtib3gtc2hhZG93OjAgNHB4IDE4cHggcmdiYSh2YXIoLS1jeSksLjMpfQpi
b2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtYXNrIGJ1dHRvbi5hbHR7YmFja2dyb3VuZDpyZ2JhKDI1NSwyNTUsMjU1LC4wNyk7Ym94LXNoYWRvdzpub25lO2JvcmRlcjoxcHggc29saWQgdmFyKC0taHYtYik7Y29sb3I6I2YxZGZkNn0KYm9keVtkYXRhLXBhZ2U9aG9t
ZV0gLmh4LWhpdHN7bWFyZ2luLXRvcDoxMnB4fQovKiDRgdC+0LHRi9GC0LjRjyDQutCw0Log0LvQtdC90YLQsCBMaW5lYXIgKi8KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LWV2e3BhZGRpbmc6MjBweCAyMnB4O2Rpc3BsYXk6ZmxleDtmbGV4LWRpcmVjdGlvbjpj
b2x1bW59CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1ldiBoM3ttYXJnaW46MCAwIDhweDtmb250LXNpemU6MTBweDtsZXR0ZXItc3BhY2luZzouMjZlbX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LWV7cGFkZGluZzo5cHggMCA5cHggMTZweDtwb3NpdGlvbjpy
ZWxhdGl2ZTtib3JkZXItdG9wOjFweCBzb2xpZCByZ2JhKDI1NSwxNjAsMTIwLC4wOSk7Zm9udC1zaXplOjEzcHh9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1lOjpiZWZvcmV7Y29udGVudDonJztwb3NpdGlvbjphYnNvbHV0ZTtsZWZ0OjA7dG9wOjE1cHg7d2lk
dGg6NnB4O2hlaWdodDo2cHg7Ym9yZGVyLXJhZGl1czo1MCU7YmFja2dyb3VuZDpyZ2IodmFyKC0tYW0pKTtib3gtc2hhZG93OjAgMCA4cHggcmdiYSh2YXIoLS1hbSksLjYpfQovKiDQv9C70LjRgtC60Lgg0LHRi9GB0YLRgNGL0YUg0LTQtdC50YHRgtCy0LjQuSAo
dmlzaW9uT1MpICovCmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1re21hcmdpbjo2cHggNHB4IDA7Zm9udC1zaXplOjEwcHg7bGV0dGVyLXNwYWNpbmc6LjNlbX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LXFhe2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQo
YXV0by1maWxsLG1pbm1heCgxMDRweCwxZnIpKTtnYXA6MTJweDttYXJnaW46MH0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LXFhIGF7ZmxleC1kaXJlY3Rpb246Y29sdW1uO2p1c3RpZnktY29udGVudDpjZW50ZXI7Z2FwOjlweDttaW4taGVpZ2h0OjEwMHB4O3Bh
ZGRpbmc6MTJweCA2cHg7Ym9yZGVyLXJhZGl1czoyNHB4O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQ6NTAwIDExLjVweC8xLjIgdmFyKC0tYm9keSxpbmhlcml0KTtsZXR0ZXItc3BhY2luZzouMDJlbTt0ZXh0LXRyYW5zZm9ybTpub25lO2NvbG9yOiNmMWRmZDY7dHJh
bnNpdGlvbjp0cmFuc2Zvcm0gLjE4cyBjdWJpYy1iZXppZXIoLjIsLjgsLjIsMSksYmFja2dyb3VuZCAuMTVzLGJvcmRlci1jb2xvciAuMTVzfQpib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtcWEgYSBzbC1pY29ue2ZvbnQtc2l6ZToyOHB4O2NvbG9yOiNmZmQ5YzQ7
d2lkdGg6NTJweDtoZWlnaHQ6NTJweDtkaXNwbGF5OmdyaWQ7cGxhY2UtaXRlbXM6Y2VudGVyO2JvcmRlci1yYWRpdXM6MTZweDtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCgxNjBkZWcscmdiYSh2YXIoLS1hbSksLjI4KSxyZ2JhKHZhcigtLWN5KSwuMTgpKTti
b3gtc2hhZG93Omluc2V0IDAgMXB4IDAgcmdiYSgyNTUsMjU1LDI1NSwuMTgpfQpib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtcWEgYTpob3Zlcnt0cmFuc2Zvcm06dHJhbnNsYXRlWSgtM3B4KSBzY2FsZSgxLjAzKTtiYWNrZ3JvdW5kOnJnYmEodmFyKC0tY3kpLC4x
Nik7Ym9yZGVyLWNvbG9yOnJnYmEodmFyKC0tY3kpLC41KX0KLyog0YHQstC+0LTQutCwINC4INGB0LvRg9C20LHRiyAqLwpib2R5W2RhdGEtcGFnZT1ob21lXSBzZWN0aW9uLmNhcmRbYXJpYS1sYWJlbD3QodCy0L7QtNC60LBde3BhZGRpbmc6MTBweCAxOHB4O2Jv
cmRlci1yYWRpdXM6MTZweH0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLnN1bXtnYXA6MTJweH0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gI3N1bVRleHR7Zm9udC1zaXplOjEycHghaW1wb3J0YW50O2xldHRlci1zcGFjaW5nOi4xZW0haW1wb3J0YW50fQpib2R5W2RhdGEt
cGFnZT1ob21lXSAuZ3JpZHtnYXA6MTJweH0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmNhcmQuc3Zje3BhZGRpbmc6MTZweCAxOHB4IDE0cHg7bWluLWhlaWdodDowfQpib2R5W2RhdGEtcGFnZT1ob21lXSAuc3ZjLWh7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNl
bnRlcjtnYXA6OXB4fQpib2R5W2RhdGEtcGFnZT1ob21lXSAuc3ZjLWggYntmb250OjYwMCAxNHB4IHZhcigtLWJvZHksaW5oZXJpdCk7bGV0dGVyLXNwYWNpbmc6LjAyZW07dGV4dC10cmFuc2Zvcm06bm9uZX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLnN2Yy1oIC5t
c3ttYXJnaW4tbGVmdDphdXRvO2ZvbnQtc2l6ZToxMHB4O2NvbG9yOnZhcigtLW11MiwjOWM4Mjc5KX0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLnN2Yy1zdWJ7Zm9udC1zaXplOjExcHg7bWFyZ2luOjJweCAwIDhweH0KYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmxpbmVz
IGxpe2ZvbnQtc2l6ZToxMi41cHh9CmJvZHlbZGF0YS1wYWdlPWhvbWVdIC5zdmMtc3R7bWFyZ2luLXRvcDoxMHB4O2ZvbnQtc2l6ZToxMHB4O2xldHRlci1zcGFjaW5nOi4xNmVtfQpib2R5W2RhdGEtcGFnZT1ob21lXSAuY2FyZD5oMixib2R5W2RhdGEtcGFnZT1o
b21lXSAuY2FyZCAuaDJ7Zm9udC1zaXplOjEwcHg7bGV0dGVyLXNwYWNpbmc6LjI0ZW07bWFyZ2luLWJvdHRvbToxMHB4fQovKiDQvNC+0LHQuNC70YzQvdCw0Y86IDM5MCAqLwpAbWVkaWEgKG1heC13aWR0aDo4NjBweCl7Ym9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4
LWhlcm97Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmcn19CkBtZWRpYSAobWF4LXdpZHRoOjU2MHB4KXsKIGJvZHlbZGF0YS1wYWdlPWhvbWVdIC53cmFwe3dpZHRoOmNhbGMoMTAwJSAtIDIwcHgpO2dhcDoxMHB4fQogYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LWhp
e3BhZGRpbmc6MThweCAxNnB4IDE2cHh9CiBib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtaHtmb250LXNpemU6MjZweDtsZXR0ZXItc3BhY2luZzouMWVtfQogYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LXN1YnttYXJnaW4tYm90dG9tOjE0cHg7Zm9udC1zaXplOjEz
cHh9CiBib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtYXNre21pbi1oZWlnaHQ6NTRweDtwYWRkaW5nLWxlZnQ6NDRweDtib3JkZXItcmFkaXVzOjE3cHh9CiBib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtYXNrOjpiZWZvcmV7bGVmdDoxNXB4fWJvZHlbZGF0YS1wYWdl
PWhvbWVdIC5oeC1hc2s6OmFmdGVye2xlZnQ6MjhweH0KIGJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1hc2sgaW5wdXR7Zm9udC1zaXplOjE2cHh9CiBib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtYXNrIGJ1dHRvbntwYWRkaW5nOjAgMTRweDttaW4taGVpZ2h0OjQ0
cHh9CiBib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtYXNrIGJ1dHRvbi5hbHR7ZGlzcGxheTpub25lfQogYm9keVtkYXRhLXBhZ2U9aG9tZV0gLmh4LXFhe2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoNCwxZnIpO2dhcDo4cHh9CiBib2R5W2RhdGEtcGFnZT1o
b21lXSAuaHgtcWEgYXttaW4taGVpZ2h0Ojg4cHg7Ym9yZGVyLXJhZGl1czoyMHB4O2ZvbnQtc2l6ZToxMC41cHg7cGFkZGluZzoxMHB4IDJweH0KIGJvZHlbZGF0YS1wYWdlPWhvbWVdIC5oeC1xYSBhIHNsLWljb257d2lkdGg6NDRweDtoZWlnaHQ6NDRweDtmb250
LXNpemU6MjNweDtib3JkZXItcmFkaXVzOjE0cHh9CiBib2R5W2RhdGEtcGFnZT1ob21lXSAuaHgtZXZ7cGFkZGluZzoxNnB4fQp9Cg==
S1EOF
echo OK nox-home-v.css $(wc -c <nox-home-v.css)
cd /workspace/nox/web/site
cp -n index.html index.html.bak_s1_1
grep -q nox-home-v.css index.html || sed -i 's#<link rel="stylesheet" href="./nox-home-x.css?v=2">#<link rel="stylesheet" href="./nox-home-x.css?v=2"><link rel="stylesheet" href="./nox-home-v.css?v=1">#' index.html
sed -i 's#nox-home-v.css?v=[0-9]*#nox-home-v.css?v='$(date +%s)'#' index.html
grep -c "nox-home-v.css" index.html
cd /tmp; /workspace/nox/venv/bin/python /workspace/nox/tools/s1_shot.py index.html hm2 vp=pc,mob 2>&1 | cut -c1-900
