import json,sys,itertools
from playwright.sync_api import sync_playwright
AXE=open('/workspace/nox/tools/uiscore/node_modules/axe-core/axe.min.js').read()
W=['helion','chronos','somnium','forge','synapse'];P=['gold','copper','glacier','ion','amethyst','platinum'];M=['metal','gear','liquid','glass','plasma','mineral']
pages=sys.argv[1:] or ['settings','system','studio','chat-dc']
SET="""([w,p,m])=>{const H=document.documentElement;const E=window.NOX_CINEMATIC_WORLDS;
 if(E){if(w)E.setWorld(w);if(p)E.setPalette(p)}else{if(w)H.dataset.noxWorld=w;if(p)H.dataset.noxColor=p}
 if(m)H.dataset.noxUiButton=m;return 1}"""
OBS="""()=>{const H=document.documentElement,cs=getComputedStyle(H);
 const b=[...document.querySelectorAll('button,a.btn,sl-button')].find(x=>{const r=x.getBoundingClientRect();return r.width>40&&r.height>20&&r.top>=0});
 const bc=b?getComputedStyle(b):null;
 return {world:H.dataset.noxWorld||null,color:H.dataset.noxColor||null,btn:H.dataset.noxUiButton||null,rgb:cs.getPropertyValue('--nox-world-rgb').trim(),bg:getComputedStyle(document.body).backgroundColor,
  theme:H.dataset.noxTheme||H.dataset.theme||null,b:bc?[bc.backgroundColor,bc.color,bc.borderRadius,bc.boxShadow.slice(0,40)]:null,hs:document.documentElement.scrollWidth>innerWidth+2}}"""
AX="axe.run(document,{runOnly:['color-contrast'],resultTypes:['violations']}).then(r=>r.violations.flatMap(v=>v.nodes.map(n=>[n.target.join(' ').slice(0,60),(n.any[0]&&n.any[0].data&&(n.any[0].data.contrastRatio+'|'+n.any[0].data.fgColor+'|'+n.any[0].data.bgColor))||''])))"
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    for n in pages:
        for vw,vh in ((1920,1080),(390,844)):
            pg=b.new_page(viewport={'width':vw,'height':vh},is_mobile=vw<500,has_touch=vw<500)
            try:
                pg.goto('http://127.0.0.1:18091/web/%s.html'%n,wait_until='load',timeout=60000);pg.wait_for_timeout(3500);pg.add_script_tag(content=AXE)
            except Exception as e:
                print(json.dumps({'page':n,'vp':vw,'err':str(e)[:80]}));continue
            combos=[(w,pp,None) for w in W for pp in P]+[(None,None,m) for m in M]
            base=None
            for c in combos:
                try:
                    pg.evaluate(SET,list(c));pg.wait_for_timeout(250)
                    o=pg.evaluate(OBS);ax=pg.evaluate(AX)
                    print(json.dumps({'page':n,'vp':vw,'c':c,'o':o,'cc':len(ax),'ex':ax[:2]},ensure_ascii=False),flush=True)
                except Exception as e:
                    print(json.dumps({'page':n,'vp':vw,'c':c,'err':str(e)[:80]}),flush=True)
            pg.close()
    b.close()
print('MATRIX_DONE')
