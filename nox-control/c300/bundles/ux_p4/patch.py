import sys,os
f='nox-k4-core.js'
a="document.head.appendChild(l)}"
add="\n if(!document.getElementById('ux-fab-js')){const s=document.createElement('script');s.id='ux-fab-js';s.src='./nox-ux-fab.js?v=ux1';s.defer=true;document.head.appendChild(s)}"
s=open(f,encoding='utf-8').read()
if 'ux-fab-js' in s: print('ALREADY')
elif a in s:
    i=s.rindex(a)+len(a); open(f+'.bak_ux_'+sys.argv[1],'w',encoding='utf-8').write(s); open(f,'w',encoding='utf-8').write(s[:i]+add+s[i:]); print('PATCHED')
else: print('MISS')
