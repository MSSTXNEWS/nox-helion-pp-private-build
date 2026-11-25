import sys,os
R=[
('qa.html','<body><main><h1>Контроль канона</h1>','<body><div id="app"><main><h1>Контроль канона</h1>'),
('qa.html','<div class="g" id="g"></div></main>','<div class="g" id="g"></div></main></div>'),
('board.html','<script src="./vendor/nox-x/excalidraw/dist/excalidraw.production.min.js"></script>',"<script>window.EXCALIDRAW_ASSET_PATH='./vendor/nox-x/excalidraw/dist/';</script><script src=\"./vendor/nox-x/excalidraw/dist/excalidraw.production.min.js\"></script>"),
]
for f,a,b in R:
    if not os.path.exists(f): print('NOFILE',f); continue
    s=open(f,encoding='utf-8').read()
    if a in s and b not in s: open(f+'.bak_ux_'+sys.argv[1],'w',encoding='utf-8').write(s); open(f,'w',encoding='utf-8').write(s.replace(a,b,1)); print('PATCHED',f)
    elif b in s: print('ALREADY',f)
    else: print('MISS',f)
