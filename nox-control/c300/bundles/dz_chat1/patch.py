import sys,re
S=sys.argv[1]; f=S+'/chat-dc.html'; h=open(f).read()
if 'nox-dc-wow.css' not in h:
    h=h.replace('<link rel="stylesheet" href="./nox-dc.css?v=dc11">','<link rel="stylesheet" href="./nox-dc.css?v=dc11">\n<link rel="stylesheet" href="./nox-worlds.css"><link rel="stylesheet" href="./nox-dc-wow.css?v=w1">',1)
h=re.sub(r'nox-dc-fill\.js\?v=\w+','nox-dc-fill.js?v=w1',h)
if 'nox-dc-wow.js' not in h:
    h=h.replace('<script src="./nox-dc-fill.js?v=w1" defer></script>','<script src="./nox-dc-fill.js?v=w1" defer></script><script src="./nox-dc-wow.js?v=w1" defer></script><script src="./nox-worlds.js" defer></script><script type="module" src="./nox-fx.js"></script><script src="./nox-reveal.js" defer></script>',1)
open(f,'w').write(h); print('patched', h.count('nox-dc-wow'))
