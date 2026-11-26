import sys,re,os
S=sys.argv[1].rstrip('/')+'/'
def rd(f):
    return open(S+f).read()
def wr(f,t,bak='.bak_rv1'):
    if not os.path.exists(S+f+bak): open(S+f+bak,'w').write(rd(f))
    open(S+f,'w').write(t)
# 1. a11y-fix: цели 44 px (шапка, sl-button, nav на мобильном, excalidraw, вкладки assistant, ползунки)
CSS=("html body .tb-i,html body button.tb-i{min-width:44px!important;min-height:44px!important}"
 "html body sl-button{min-height:44px!important}"
 "@media(max-width:700px){html body nav a{min-height:44px!important;box-sizing:border-box}}html body .fc-button{min-width:44px!important;min-height:44px!important}html body .excalidraw input.ToolIcon_type_checkbox{min-width:44px!important}"
 "html body .excalidraw button,html body .excalidraw .ToolIcon__icon,html body .excalidraw .ToolIcon input,html body .excalidraw .help-icon{min-width:44px}"
 "html body #fTabs button{min-height:44px}"
 "html body input[type=range]{min-height:44px}"
 "html body sl-range{min-height:44px}html body sl-range::part(base){min-height:44px;display:flex;align-items:center}"
 "html body sl-range::part(input){min-height:44px}")
f='nox-a11y-fix.js'; t=rd(f)
if 'rvfix1' not in t:
    t+="\n/*rvfix1*/(function(){if(/[?&]a11y=0/.test(location.search))return;var s=document.createElement('style');s.textContent=%r;document.head.appendChild(s)})();\n"%CSS
    wr(f,t); print('a11y ok')
# 2. deep-chat: новые имена позиций
f='nox-dc.js'
if os.path.exists(S+f):
    t=rd(f); n=t
    for a,b in (('inside-left','inside-start'),('inside-right','inside-end'),('outside-left','outside-start'),('outside-right','outside-end')): n=n.replace("'"+a+"'","'"+b+"'").replace('"'+a+'"','"'+b+'"')
    if n!=t: wr(f,n); print('dc positions ok')
# 3. assistant: anonymous define (vis-timeline = 2 UMD в одном файле при глобальном AMD define)
f='assistant.html'; t=rd(f)
tag='<script src="./vendor/v7/vistimeline/vis-timeline-graph2d.min.js"></script>'
if tag in t and 'rvdef' not in t:
    t=t.replace(tag,'<script>window.__rvdef=window.define;window.define=void 0</script>'+tag+'<script>window.define=window.__rvdef</script>',1); wr(f,t); print('assistant ok')
# 4. voice: select -> плитки
f='voice.html'; t=rd(f)
if 'nox-select-tiles.js' not in t and os.path.exists(S+'nox-select-tiles.js'):
    t=t.replace('</body>','<script src="./nox-select-tiles.js?v=rv1" defer></script></body>',1); wr(f,t); print('voice tiles ok')
# 5. motion.js: два анонимных define при глобальном AMD loader (monaco) -> прячем define на время файла
f='vendor/fx/motion.js'
if os.path.exists(S+f):
    t=rd(f)
    if 'rvdef' not in t:
        wr(f,"var __rvdef=window.define;window.define=void 0;\n"+t+"\n;window.define=__rvdef;/*rvdef*/\n"); print('motion ok')
