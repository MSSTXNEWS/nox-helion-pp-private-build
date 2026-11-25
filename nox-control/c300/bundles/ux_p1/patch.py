# ux_p1: точечные правки юзабилити; идемпотентно, ничего не перезаписывает целиком
import re,sys,os
R=[
('nox-pages.css','font:400 10.5px/1.3 var(--mono);letter-spacing:.26em','font:400 12px/1.3 var(--mono);letter-spacing:.2em'),
('nox-hud-s1.css','font:10px/1 var(--mono,monospace);letter-spacing:.14em','font:12px/1 var(--mono,monospace);letter-spacing:.1em'),
('nox-k6-dash.js',"'Дашборд','grid-1x2'","'Дашборд','layout-grid'"),
('nox-k6-canvasdoc.js',"'Canvas','file-earmark-text'","'Canvas','file-text'"),
('nox-k6-board.js',"'Холст','bounding-box'","'Холст','box-model'"),
('nox-k6-mindmap.js',"'Карта темы','diagram-3'","'Карта темы','hierarchy-2'"),
('nox-s6-cinema.js','name="player-play-filled"','name="player-play"'),
('nox-pages.css','.big small{font:400 11px/1','.big small{font:400 12px/1'),
('nox-p-system.js',"const d = r.data, g = d.gpu || {};","const d = r.data; ['gpu', 'cpu', 'cpu_temp', 'ram', 'shm'].forEach((k) => { if (!d[k] || typeof d[k] !== 'object') d[k] = { error: 'нет данных' }; }); const g = d.gpu || {};"),
]
ok=0
for f,a,b in R:
    if not os.path.exists(f): print('NOFILE',f); continue
    s=open(f,encoding='utf-8').read()
    if a in s: open(f+'.bak_ux_'+sys.argv[1],'w',encoding='utf-8').write(s); open(f,'w',encoding='utf-8').write(s.replace(a,b)); print('PATCHED',f); ok+=1
    elif b in s: print('ALREADY',f)
    else: print('MISS',f)
