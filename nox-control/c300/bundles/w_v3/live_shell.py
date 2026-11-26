import sys
S=sys.argv[1] if len(sys.argv)>1 else '/workspace/nox/web/site/'
HEAD='''<script src="./nox-theme.js"></script>
<script type="importmap">{"imports":{"three":"./vendor/three/build/three.module.js","postprocessing":"./vendor/postprocessing/build/index.js"}}</script>
<link rel="stylesheet" href="./nox-fx.css"><script type="module" src="./nox-fx.js"></script>
<link rel="stylesheet" href="./nox-worlds.css"><script src="./nox-worlds.js"></script>
<link rel="stylesheet" href="./nox-s4-glass.css"><link rel="stylesheet" href="./nox-4k.css">
<link rel="stylesheet" href="./nox-ds.css?v=s3c"><script src="./nox-ds.js?v=s3f" defer></script>
<link rel="stylesheet" href="./nox-m-mobile.css?v=m1000" media="(max-width:768px)"><script src="./nox-m-mobile.js?v=u1" defer></script>
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
h=h.replace(k,k+'\n'+HEAD,1).replace('</html>',BODY+'</html>',1)
open(f,'w').write(h); print('live shell added')
