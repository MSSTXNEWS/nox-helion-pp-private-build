S=/workspace/nox/web/site
cd $S
SRC=$(dirname $(readlink -f /tmp/c300.sh 2>/dev/null || echo /tmp/c300.sh))
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in nox-chat-tg.css nox-chat-tg.js; do [ -f $f ] && cp -p $f $f.bak_s1_$(date +%H%M%S); curl -fsSL "$R/$f?$(date +%s)" -o /tmp/$f && cp /tmp/$f $f && echo OK $f $(wc -c <$f) || echo FAIL $f; done
[ -f chat.html.bak_s1_2 ] || cp -p chat.html chat.html.bak_s1_2
grep -q nox-chat-tg.css chat.html || sed -i 's#</head>#<link rel="stylesheet" href="/web/nox-chat-tg.css?v=1"></head>#' chat.html
grep -q nox-chat-tg.js chat.html || sed -i 's#</body>#<script src="/web/nox-chat-tg.js?v=1" defer></script></body>#' chat.html
grep -c "nox-chat-tg" chat.html
mkdir -p /workspace/nox/tools
cat > /workspace/nox/tools/s1_shot.py <<'P'
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
    b=base64.b64encode(open(j,'rb').read()).decode()
    print('B64_%s_BEGIN'%tag)
    for i in range(0,len(b),900): print(b[i:i+900])
    print('B64_%s_END'%tag)
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
                pg.fill('#input','привет'); pg.keyboard.press('Enter')
                for i in range(40):
                    pg.wait_for_timeout(2000)
                    t=pg.evaluate("(()=>{const a=[...document.querySelectorAll('#msgs .m.a .txt')].pop();return a?a.innerText:''})()")
                    if t and 'ОЖИДАНИЕ' not in t and not pg.evaluate("document.body.classList.contains('nox-busy')"): break
                print('REPLY',json.dumps(t,ensure_ascii=False)[:300])
                print('BUBBLE_ERR',pg.evaluate("!!document.querySelector('.bubble.err')"))
            except Exception as e: print('SENDERR',e)
        pg.screenshot(path='/tmp/s.png')
        out(L+'_'+name,'/tmp/s.png',1100 if w>1500 else w)
        print('ERRS',name,errs[:4]); print('BAD',name,bad[:12])
        ctx.close()
    b.close()

P
cd /tmp; /workspace/nox/venv/bin/python /workspace/nox/tools/s1_shot.py chat.html tg1 send 2>&1 | cut -c1-900
