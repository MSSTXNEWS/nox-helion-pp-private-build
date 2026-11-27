import sys
S=sys.argv[1]; pages=sys.argv[2:]
TAG='<script src="./nox-jarvis-layer.js?v=j1" defer></script>'
for p in pages:
    f=S+'/'+p+'.html'
    try: h=open(f).read()
    except Exception: print('no',p); continue
    if 'nox-jarvis-layer' in h: print('already',p); continue
    open(f+'.bak_jv2','w').write(h)
    open(f,'w').write(h.replace('</body>',TAG+'</body>',1)); print('tagged',p)
