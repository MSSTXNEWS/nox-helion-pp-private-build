import sys
f='nox-dock-pop.js'; s=open(f,encoding='utf-8').read()
if 'ux-fab-js' in s: print('ALREADY')
else:
    open(f+'.bak_ux_'+sys.argv[1],'w',encoding='utf-8').write(s)
    open(f,'w',encoding='utf-8').write(s.rstrip('\n')+"\n;(function(){if(!document.getElementById('ux-fab-js')){var s=document.createElement('script');s.id='ux-fab-js';s.src='./nox-ux-fab.js?v=ux1';s.defer=true;document.head.appendChild(s)}})();\n"); print('PATCHED')
