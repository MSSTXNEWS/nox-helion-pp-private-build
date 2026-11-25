import sys,os
R=[
('projects.html','<form class="dlg" id="dForm" autocomplete="off">','<form class="dlg" id="dForm" autocomplete="off" novalidate>'),
('nox-p-projects.js',"if (!title) { $('#dTitle').focus(); return; }","if (!title) { $('#dTitle').setAttribute('aria-invalid', 'true'); toast('Введите название', true); $('#dTitle').focus(); return; }"),
('nox-atlas-s1.css','color:var(--mu,#c2a9a0);font-size:11.5px','color:var(--mu,#c2a9a0);font-size:12px'),
('nox-k6-slides.js',"'Слайды','easel'","'Слайды','presentation'"),
]
for f,a,b in R:
    if not os.path.exists(f): print('NOFILE',f); continue
    s=open(f,encoding='utf-8').read()
    if a in s: open(f+'.bak_ux_'+sys.argv[1],'w',encoding='utf-8').write(s); open(f,'w',encoding='utf-8').write(s.replace(a,b)); print('PATCHED',f)
    elif b in s: print('ALREADY',f)
    else: print('MISS',f)
