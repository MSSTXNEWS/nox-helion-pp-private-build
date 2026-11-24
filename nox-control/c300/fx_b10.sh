S=/workspace/nox/web/site; T=bak_fx_b8
[ -f $S/nox-api.js.$T ] || cp $S/nox-api.js $S/nox-api.js.$T
/workspace/nox/venv/bin/python - <<'PYEOF'
import re,os,glob,shutil
S='/workspace/nox/web/site'; T='bak_fx_b8'
def rd(p): return open(p,encoding='utf-8').read()
def wr(p,t): open(p,'w',encoding='utf-8').write(t)
# timeouts / honest slow core
t=rd(S+'/nox-api.js')
t=t.replace("call('/glm/v1/nox/stats'), call('/glm/v1/models'), call('/api/chat/health'), call('/stt/health')","call('/glm/v1/nox/stats', { timeout: 20000 }), call('/glm/v1/models'), call('/api/chat/health', { timeout: 20000 }), call('/stt/health')")
t=t.replace("const ch = chat.ok && chat.data ? chat.data : null, up =","const slow = /timed out|timeout|abort/i.test(stats.error || ''), ch = chat.ok && chat.data ? chat.data : null, up =")
t=t.replace("state: !H ? 'bad' : F && F.ok > 0 ? 'ok' : 'warn', ms: stats.ms, error: !H ? 'ядро недоступно: '","state: !H ? (slow ? 'warn' : 'bad') : F && F.ok > 0 ? 'ok' : 'warn', ms: stats.ms, error: !H ? (slow ? 'ядро занято: ответ дольше 20 с · ' : 'ядро недоступно: ')")
t=t.replace("state: !org ? 'bad' : org.memory ? 'ok' : 'warn', ms: stats.ms, error: !org ? 'ядро недоступно'","state: !org ? (slow ? 'warn' : 'bad') : org.memory ? 'ok' : 'warn', ms: stats.ms, error: !org ? (slow ? 'ядро занято, ответ дольше 20 с' : 'ядро недоступно')")
wr(S+'/nox-api.js',t)
CSS="""<style>
.page section.card h2{font-size:13px;letter-spacing:.14em;text-transform:uppercase;margin:0 0 10px;font-weight:600}
.page ul{list-style:none;margin:0;padding:0}.page li{padding:9px 0;border-bottom:1px solid rgba(255,255,255,.07);display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}.page li:last-child{border-bottom:0}
.page .name{flex:1 1 220px}.page .note{color:rgba(230,220,210,.55);font-size:13px;width:100%}
.page .badge{font-size:11px;letter-spacing:.07em;padding:3px 9px;border-radius:999px;border:1px solid;white-space:nowrap}
.b-live{color:#9fd8a4;border-color:rgba(100,180,110,.5)}.b-des{color:#b4c2d0;border-color:rgba(160,180,200,.4)}.b-ni{color:#e5a090;border-color:rgba(220,120,100,.5)}.b-hold{color:#e5cf90;border-color:rgba(220,190,110,.5)}
.page pre{background:rgba(0,0,0,.38);border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:10px;overflow:auto;max-height:320px;font-size:12.5px;white-space:pre-wrap;word-break:break-word}
.page .btn{min-height:44px;padding:0 16px;border-radius:10px;border:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.07);color:#f0e4da;font:inherit;cursor:pointer}
.page .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:8px 0}
.page textarea,.page input[type=text]{width:100%;box-sizing:border-box;background:rgba(0,0,0,.4);color:inherit;border:1px solid rgba(255,255,255,.14);border-radius:10px;padding:10px;font:inherit;min-height:44px}
.page img{max-width:100%;border-radius:10px;margin-top:10px}.page .quote{font-style:italic;opacity:.75;border-left:2px solid rgba(214,70,48,.5);padding-left:12px;margin:10px 0}
.page label{font-size:13px;opacity:.85}.page .purpose{margin:0 0 14px;opacity:.8}
</style>"""
HEAD="""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>@@T@@</title>
<link rel="icon" href="favicon.svg">
<link rel="stylesheet" href="./vendor/fonts-wow/fonts.css">
<link rel="stylesheet" href="./vendor/shoelace/cdn/themes/dark.css">
<link rel="stylesheet" href="./nox-wow.css">
<link rel="stylesheet" href="./nox-pages.css">
<link rel="stylesheet" href="./nox-unify.css">
<script src="./nox-theme.js"></script>
<script type="importmap">{"imports":{"three":"./vendor/three/build/three.module.js","postprocessing":"./vendor/postprocessing/build/index.js"}}</script>
"""+CSS+"""</head>
<body data-page="@@D@@" class="boot">
<div id="app">
<main class="page" id="page"><div class="wrap">
"""
done=[];skip=[]
for f in sorted(glob.glob(S+'/*.html')):
    n=os.path.basename(f); t=rd(f)
    if 'nox-nav.js' in t: continue
    if n in('tv.html','planets.html','resonance.html'): continue
    m=re.search(r'<main>(.*?)</main>',t,re.S); tt=re.search(r'<title>(.*?)</title>',t,re.S); dp=re.search(r'<body[^>]*data-page="([^"]*)"',t)
    if not m or not tt or '<header>' not in t: skip.append(n); continue
    mi=m.group(1)
    c=re.search(r'<div class="canon">(.*?)</div>',mi,re.S); h=re.search(r'<h1>(.*?)</h1>',mi,re.S); pu=re.search(r'<p class="purpose">(.*?)</p>',mi,re.S)
    if not h: skip.append(n); continue
    rest=mi
    for x in (c,h,pu):
        if x: rest=rest.replace(x.group(0),'',1)
    rest=rest.replace('<section>','<section class="card">')
    tail=t[m.end():]
    tail=tail.replace("badge('LIVE'); show('livebody', txt.slice(0,3000));","var st='DESIGNED';try{var jj=JSON.parse(txt);if(jj&&jj.status)st=String(jj.status)}catch(e){} badge(st); show('livebody', txt.slice(0,3000));")
    tail=tail.replace('</body></html>','</body>\n</html>')
    tail=re.sub(r'^\s*','',tail)
    out=HEAD.replace('@@T@@',tt.group(1)).replace('@@D@@',dp.group(1) if dp else n[:-5])
    out+='<div class="ph"><div><span class="kick mono">%s</span><h1>%s</h1></div></div>\n'%(c.group(1) if c else '',h.group(1))
    if pu: out+='<p class="purpose">%s</p>\n'%pu.group(1)
    out+=rest.strip()+'\n</div></main>\n</div>\n<script type="module" src="./nox-nav.js"></script>\n'+tail
    shutil.copy2(f,f+'.'+T); wr(f,out); done.append(n)
print('CONVERTED',len(done),done); print('SKIPPED',skip)
# planets / resonance
for n,h1,txt,extra in (('planets','Планеты','Выберите планету из списка. Доступны реальные планеты с фото-текстурами.','<a class="btn" href="settings.html" style="display:inline-flex;align-items:center;text-decoration:none">Перейти к настройкам</a>'),('resonance','Страница перенесена','Раздел «Резонанс» теперь называется «Чат». Через несколько секунд откроется чат.','<a class="btn" href="chat.html" style="display:inline-flex;align-items:center;text-decoration:none">Открыть чат</a>')):
    f='%s/%s.html'%(S,n); t=rd(f)
    if 'nox-nav.js' in t: continue
    shutil.copy2(f,f+'.'+T)
    refresh='<meta http-equiv="refresh" content="4;url=chat.html">' if n=='resonance' else ''
    out=(HEAD.replace('@@T@@','NOX HELION · '+h1.upper()).replace('@@D@@',n)).replace('<link rel="icon"',refresh+'<link rel="icon"',1)
    out+='<div class="ph"><div><span class="kick mono">NOX HELION</span><h1>%s</h1></div></div>\n<section class="card"><p>%s</p><div class="row">%s</div></section>\n</div></main>\n</div>\n<script type="module" src="./nox-nav.js"></script>\n<script src="./nox-dock-pop.js" defer></script>\n<script type="module" src="./nox-ninja.js"></script>\n<script src="./nox-minichat.js" defer></script>\n<link rel="manifest" href="./manifest.json"><script src="./nox-pwa.js" defer></script>\n</body>\n</html>\n'%(h1,txt,extra)
    wr(f,out); print('special',n)
# tv
f=S+'/tv.html'; t=rd(f)
if 'nox-nav.js' not in t:
    shutil.copy2(f,f+'.'+T)
    t=t.replace('<link rel="stylesheet" href="./vendor/fonts-wow/fonts.css">','<link rel="stylesheet" href="./vendor/fonts-wow/fonts.css">\n<link rel="stylesheet" href="./nox-wow.css">\n<link rel="stylesheet" href="./nox-unify.css">\n<script src="./nox-theme.js"></script>\n<script type="importmap">{"imports":{"three":"./vendor/three/build/three.module.js","postprocessing":"./vendor/postprocessing/build/index.js"}}</script>',1)
    t=t.replace('html,body{margin:0;height:100%;background:radial-gradient(ellipse at 30% 20%,#0d1a33 0%,#03050c 55%,#000 100%);color:#e6f1ff;font-family:system-ui,sans-serif;overflow:hidden}','html,body{margin:0;height:100%;background:#000;color:#e6f1ff;font-family:system-ui,sans-serif;overflow:hidden}')
    t=t.replace('#stars{position:fixed;inset:0;pointer-events:none}','#stars{display:none}')
    t=t.replace('#chat{position:fixed;inset:5vh 6vw;','#chat{position:fixed;z-index:5;inset:84px 6vw 130px;')
    t=t.replace('<body>','<body data-page="tv" class="boot">\n<div id="app"><main class="page" id="page"></main></div>',1)
    t=t.replace('</body>','<script type="module" src="./nox-nav.js"></script>\n</body>',1)
    wr(f,t); print('special tv', 'nox-nav.js' in t)
PYEOF
grep -n "fetch\|HEAD" $S/nox-p-about.js | cut -c1-260 | head -8
cat > /tmp/sh2.py <<'P'
import base64,subprocess,sys
from playwright.sync_api import sync_playwright
def out(tag,png,w):
    j='/tmp/s_%s.jpg'%tag
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v','11',j])
    b=base64.b64encode(open(j,'rb').read()).decode()
    print('B64_%s_BEGIN'%tag)
    for i in range(0,len(b),900): print(b[i:i+900])
    print('B64_%s_END'%tag)
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-webgl','--ignore-gpu-blocklist'])
    for n in sys.argv[1].split(','):
      for mob in (0,1):
        pg=b.new_page(viewport={'width':390,'height':844} if mob else {'width':1440,'height':900}, has_touch=bool(mob), is_mobile=bool(mob)); e=[]
        pg.on('pageerror',lambda x:e.append(str(x)[:100])); pg.on('response',lambda r: e.append('%s %s'%(r.status,r.url[-50:])) if r.status>=400 else None)
        pg.goto('http://127.0.0.1:8091/web/%s.html'%n,wait_until='load'); pg.wait_for_timeout(5500)
        pg.screenshot(path='/tmp/s.png'); out('%s_%s'%(n.replace('-','_'),'m' if mob else 'd'),'/tmp/s.png',390 if mob else 640); print(n,mob,e[:4]); pg.close()
    b.close()
P
cd /tmp; /workspace/nox/venv/bin/python /tmp/sh2.py advisors,tv,planets 2>&1
