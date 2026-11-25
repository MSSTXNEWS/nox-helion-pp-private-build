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
