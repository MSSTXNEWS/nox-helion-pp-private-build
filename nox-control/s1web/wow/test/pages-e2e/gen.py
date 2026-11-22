import sys,os
OUT='/tmp/claude-0/wt-pages/nox-control/s1web/wow/pages/'
HEAD='''<!doctype html>
<!-- nox-web-extras: пропустить (у страницы своё меню и панели; marker для deploy1.sh) -->
<html lang="ru" class="sl-theme-dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#02030a">
<title>NOX HELION · %(T)s</title>
<link rel="icon" href="favicon.svg">
<link rel="stylesheet" href="./vendor/fonts-wow/fonts.css">
<link rel="stylesheet" href="./vendor/shoelace/cdn/themes/dark.css">
<link rel="stylesheet" href="./vendor/swiper/swiper-bundle.min.css">
<link rel="stylesheet" href="./nox-wow.css">
<link rel="stylesheet" href="./nox-pages.css">
%(CSS)s<script src="./nox-theme.js"></script>
<script type="importmap">{"imports":{"three":"./vendor/three/build/three.module.js","postprocessing":"./vendor/postprocessing/build/index.js"}}</script>
</head>
<body data-page="%(K)s" class="boot">
<div id="app">
<main class="page" id="page"><div class="wrap">
%(BODY)s
</div></main>
</div>
%(TAIL)s<script type="module" src="./nox-nav.js"></script>
<script type="module" src="./%(JS)s"></script>
</body>
</html>
'''
def page(fn,K,T,JS,BODY,CSS='',TAIL=''):
    open(OUT+fn,'w',encoding='utf-8').write(HEAD%dict(K=K,T=T,JS=JS,BODY=BODY.strip('\n'),CSS=CSS,TAIL=TAIL))
exec(open('/tmp/st/gen/pages.py',encoding='utf-8').read())
