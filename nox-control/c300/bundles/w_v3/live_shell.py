import sys
S=sys.argv[1] if len(sys.argv)>1 else '/workspace/nox/web/site/'
HEAD='''<script src="./nox-theme.js"></script>
<script type="importmap">{"imports":{"three":"./vendor/three/build/three.module.js","postprocessing":"./vendor/postprocessing/build/index.js"}}</script>
<link rel="stylesheet" href="./nox-fx.css"><script type="module" src="./nox-fx.js"></script>
<link rel="stylesheet" href="./nox-worlds.css"><script src="./nox-worlds.js"></script>
<link rel="stylesheet" href="./nox-s4-glass.css"><link rel="stylesheet" href="./nox-4k.css">
<link rel="stylesheet" href="./nox-ds.css?v=s3c"><script src="./nox-ds.js?v=s3f" defer></script>
<link rel="stylesheet" href="./nox-m-mobile.css?v=m1000" media="(max-width:768px)"><script src="./nox-m-mobile.js?v=u1" defer></script>
<link rel="stylesheet" href="./vendor/fonts-wow/fonts.css"><link rel="stylesheet" href="./vendor/shoelace/cdn/themes/dark.css"><link rel="stylesheet" href="./nox-wow.css"><link rel="stylesheet" href="./nox-unify.css?v=s3_1795583846"><link rel="stylesheet" href="./nox-menu-x.css?v=s3_1795583846"><link rel="stylesheet" href="./nox-pages.css"><link rel="stylesheet" href="./nox-u-ux.css?v=x4"><link rel="stylesheet" href="./nox-vt.css"><link rel="stylesheet" href="./nox-k6-ui.css?v=k6a"><link rel="stylesheet" href="./nox-k7-ui.css?v=k7b"><link rel="stylesheet" href="./nox-hud-s1.css?v=1795624713">
<style id="nxLiveWow">body{background:transparent!important}.card{background:rgba(255,255,255,.05);backdrop-filter:blur(14px) saturate(1.2);-webkit-backdrop-filter:blur(14px) saturate(1.2);border:1px solid rgba(255,255,255,.12);border-radius:16px}</style>
'''
BODY='''<script type="module" src="./nox-nav.js"></script>
<script src="./nox-dock-pop.js?v=s3f" defer></script>
<script type="module" src="./nox-ninja.js"></script>
<script src="./nox-nav-x.js?v=s3_1795583846" defer></script>
<script src="./nox-sun-x.js" defer></script>
<script src="./nox-state.js" data-s3state></script>
<script src="./nox-s4-glass.js" defer></script>
<script src="./nox-s4-sl.js" defer></script>
'''
f=S+'live.html'; h=open(f).read()
if 'nxLiveWow' in h: print('live already'); sys.exit()
open(f+'.bak_v3','w').write(h)
k='<meta charset="utf-8">'
assert k in h and '</html>' in h
i=h.index('</style>')+len('</style>'); h=h[:i]+'\n<div id="app"><main class="page" id="page"><div class="wrap">'+h[i:]; j=h.rindex('<script>'); h=h[:j]+'</div></main></div>\n'+h[j:]; h=h.replace(k,k+'\n'+HEAD,1).replace('</html>',BODY+'</html>',1)
open(f,'w').write(h); print('live shell added')
