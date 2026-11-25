#!/usr/bin/env python3
"""TH: идемпотентные патчи канон-файлов на сервере. Использование: patch.py SITE_DIR"""
import sys,os
S=sys.argv[1]
def sub(fn,mark,old,new):
  p=os.path.join(S,fn)
  if not os.path.exists(p): print('MISS',fn); return
  t=open(p,encoding='utf-8').read()
  if mark in t: print('already',fn); return
  if old not in t: print('NOOLD',fn); return
  open(p,'w',encoding='utf-8').write(t.replace(old,new,1)); print('patched',fn)
# 1. сцена с солнцем не запускается в Графите
sub('nox-wow-bg.js','TH-GRAPHITE','export async function startSpace(opts) {',
 "export async function startSpace(opts) { /* TH-GRAPHITE: в «Графите» сцену с солнцем не запускаем */ if (document.documentElement.getAttribute('data-nox-theme') === 'graphite') { const n = () => {}; return { state: { texStatus: {}, level: 'off' }, setLevel: n, setPalette: n, setPlanet: n, setMood: n, dispose: n, stop: n }; }\n")
# 2. ECharts-тема nox в серых тонах
sub('nox-ds.js','TH-GRAPHITE','  const reg = () => { if (window.echarts',
 "  if (document.documentElement.getAttribute('data-nox-theme') === 'graphite') { /* TH-GRAPHITE */ Object.assign(TH, { color: ['#9db1d1', '#7fb5a8', '#c9ad7c', '#9a9cc4', '#b0b4ba', '#c98f8f'], textStyle: { color: '#edeef0', fontFamily: 'inherit', fontSize: 12 }, title: { textStyle: { color: '#edeef0', fontSize: 16, fontWeight: 400 } }, legend: { textStyle: { color: 'rgba(237,238,240,.75)', fontSize: 12 } }, tooltip: { backgroundColor: 'rgba(33,34,37,.94)', borderColor: 'rgba(255,255,255,.12)', textStyle: { color: '#edeef0', fontSize: 12 } }, categoryAxis: { axisLine: { lineStyle: { color: 'rgba(255,255,255,.16)' } }, axisLabel: { color: 'rgba(237,238,240,.7)', fontSize: 12 }, splitLine: { show: false } }, valueAxis: { axisLine: { show: false }, axisLabel: { color: 'rgba(237,238,240,.7)', fontSize: 12 }, splitLine: { lineStyle: { color: 'rgba(255,255,255,.07)' } } } }); }\n  const reg = () => { if (window.echarts")
# 3. команды палитры: смена темы
sub('nox-actions.js','TH-GRAPHITE',"    ['world.helion',",
 "    ['theme.graphite', 'Тема: Графит', 'palette', 'тема графит серый', () => window.NOXtheme && NOXtheme.set('graphite')], /* TH-GRAPHITE */\n    ['theme.sun', 'Тема: Солнце (классика)', 'sun', 'тема солнце огонь классика', () => window.NOXtheme && NOXtheme.set('sun')],\n    ['world.helion',")

# 4. иконки: резолвер библиотеки tabler берёт карту NOXiconUrl (Lucide в Графите), иначе прежний путь
OLD="resolver: (n) => new URL(V + 'tabler-icons/icons/outline/' + n + '.svg', location.href).href"
NEW="resolver: (n) => (window.NOXiconUrl ? NOXiconUrl(n, V, location.href) : new URL(V + 'tabler-icons/icons/outline/' + n + '.svg', location.href).href) /* TH-ICONS */"
for fn in ('nox-nav.js','nox-wow.js'): sub(fn,'TH-ICONS',OLD,NEW)
# 5. страницы без nox-theme.js: подключить (только <script> в head)
for fn in ('operators.html','live.html'):
  p_=os.path.join(S,fn)
  if os.path.exists(p_):
    t=open(p_,encoding='utf-8').read()
    if 'nox-theme.js' not in t and '<head>' in t:
      open(p_,'w',encoding='utf-8').write(t.replace('<head>','<head>\n<script src="./nox-theme.js"></script>',1)); print('theme-added',fn)
# 6. Filerobot: ответ сервера переводов не массив (внешний i18n, офлайн/шлюз) не должен ронять редактор
sub('vendor/nox-x/filerobot/filerobot-image-editor.min.js','Array.isArray(a.response)','(a.response||[]).forEach','(Array.isArray(a.response)?a.response:[]).forEach')

# 7. Filerobot: переводы локально (fie-i18n.json), без внешнего i18n-fastly.ultrafast.io
sub('vendor/nox-x/filerobot/filerobot-image-editor.min.js','vendor/nox-x/filerobot/fie-i18n.json','a.open("GET","https://i18n-fastly.ultrafast.io/api/export?grid=".concat(SC))','a.open("GET","./vendor/nox-x/filerobot/fie-i18n.json")')
# 8. граф памяти (cytoscape, canvas): цвета узлов, рёбер и подписей в Графите
F='nox-s4-memory.js'
sub(F,'TH-GRAPHITE-COL',"const COL = ['#e0654a', '#d9a441', '#6aa9d8', '#8fc28a', '#b48ad8', '#d68aa6', '#9a8f88'];",
 "const GX = document.documentElement.getAttribute('data-nox-theme') === 'graphite'; /* TH-GRAPHITE-COL */ const COL = GX ? ['#9db1d1', '#c9ad7c', '#7fb5a8', '#9a9cc4', '#b0b4ba', '#c98f8f', '#6f7782'] : ['#e0654a', '#d9a441', '#6aa9d8', '#8fc28a', '#b48ad8', '#d68aa6', '#9a8f88'];")
sub(F,'GX ? \'#c2d0e8\' : \'#fff\'',"c: '#fff'","c: GX ? '#c2d0e8' : '#fff'")
sub(F,"GX ? '#c2d0e8' : '#fff' }","'border-color': '#fff'","'border-color': GX ? '#c2d0e8' : '#fff'")
sub(F,"GX ? 'rgba(255,255,255,.12)'","'line-color': 'rgba(255,235,220,.18)'","'line-color': GX ? 'rgba(255,255,255,.12)' : 'rgba(255,235,220,.18)'")
sub(F,"GX ? '#b0b4ba' : '#cfc4bd'","color: '#cfc4bd'","color: GX ? '#b0b4ba' : '#cfc4bd'")

# 9. цвета-литералы в JS (графики, сцены, canvas): '#hex' / 'rgba(...)' с тёплым цветом -> (window.NOXgx ? серо-голубой : прежний). Идемпотентно (маркер TH-GXW).
import re,glob,subprocess,colorsys
ACC=(157,177,209)
def _clamp(v): return max(0,min(255,int(round(v))))
def _warm(r,g,b):
  mx=max(r,g,b)
  if mx<30 or r<g or r<b or (r-b)/max(mx,1)<.2 or (r-b)<20: return None
  h=colorsys.rgb_to_hls(r/255,g/255,b/255)[0]*360
  if not(h<=62 or h>=340): return None
  if h<=12 or h>=340:  # красный оставляем (danger/ошибка)
    return None
  L=(r*.2126+g*.7152+b*.0722)/255; ch=(mx-min(r,g,b))/255
  if ch>.5 and L>.45:
    k=min(1.15,L/.66); return (_clamp(ACC[0]*k),_clamp(ACC[1]*k),_clamp(ACC[2]*k))
  Y=L*255; return (_clamp(Y-2),_clamp(Y),_clamp(Y+5))
LIT=re.compile(r"(?<![\w$.\\/#-])(['\"])(#[0-9a-fA-F]{6}|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(?:,\s*[\d.]+\s*)?\))\1(?![\w-])")
SKIP=('nox-dz-creative.js','nox-worlds.js','nox-theme.js','nox-icons.js','nox-sun.js','nox-sun-x.js','nox-wow-bg-legacy.js','nox-wow-data.js','nox-wow-shaders.js','nox-live.js','nox-k6-live.js')
def _rep(m):
  q,c=m.group(1),m.group(2)
  if c.startswith('#'): r,g,b=int(c[1:3],16),int(c[3:5],16),int(c[5:7],16); a=None
  else:
    n=re.findall(r'[\d.]+',c); r,g,b=int(n[0]),int(n[1]),int(n[2]); a=n[3] if len(n)>3 else None
  w=_warm(r,g,b)
  if not w: return m.group(0)
  new=('#%02x%02x%02x'%w) if (c.startswith('#')) else ('rgba(%d,%d,%d,%s)'%(w+(a,)) if a is not None else 'rgb(%d,%d,%d)'%w)
  return '(window.NOXgx?%s%s%s:%s%s%s)'%(q,new,q,q,c,q)
for fp in sorted(glob.glob(os.path.join(S,'nox-*.js'))):
  b=os.path.basename(fp)
  if b in SKIP or '.bak' in b: continue
  try: t=open(fp,encoding='utf-8').read()
  except Exception: continue
  if 'TH-GXW' in t: continue
  n=LIT.sub(_rep,t)
  if n==t: continue
  tmp=fp+'.thgxw.tmp.js'; open(tmp,'w',encoding='utf-8').write(n+'\n/*TH-GXW*/\n')
  ok=True
  try: ok=subprocess.run(['node','--check',tmp],capture_output=True).returncode==0
  except Exception: ok=False
  if ok: os.replace(tmp,fp); print('gxw',b,t.count('window.NOXgx') ,len(LIT.findall(t)))
  else: os.remove(tmp); print('gxw-skip(syntax)',b)
