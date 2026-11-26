# usage: shots.py PAGE W H TAG world1,world2,..   -> montage jpg, chunked base64 in log
import sys,io,base64
from playwright.sync_api import sync_playwright
from PIL import Image
pg,W,H,tag,worlds=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),sys.argv[4],sys.argv[5].split(',')
tiles=[]; 
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
    for wd in worlds:
        c=b.new_context(viewport={'width':W,'height':H},is_mobile=(W<500)); 
        c.add_init_script("localStorage.setItem('nox.cinematic.world.v3','%s')"%wd)
        x=c.new_page(); errs=[]; x.on('pageerror',lambda e:errs.append(str(e)[:90]))
        try:
            x.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded',timeout=60000); x.wait_for_timeout(3500)
            info=x.evaluate("()=>({th:document.documentElement.getAttribute('data-nox-theme'),sel:[...document.querySelectorAll('select')].filter(e=>e.offsetWidth).length,w:!!window.NOX_CINEMATIC_WORLDS,hs:document.documentElement.scrollWidth>innerWidth+1,small:[...document.querySelectorAll('button,a,[role=button]')].filter(e=>{const r=e.getBoundingClientRect();return r.width&&r.height&&r.bottom>0&&r.top<innerHeight&&(r.height<40||r.width<40)}).length})")
            im=Image.open(io.BytesIO(x.screenshot(type='png'))).convert('RGB')
        except Exception as e: info=str(e)[:80]; im=Image.new('RGB',(W,H),(60,0,0))
        print('SH',pg,W,wd,errs[:2],info,flush=True); tiles.append(im); c.close()
    b.close()
k=len(tiles); sc=min(1.0,1500/(W*k)) if W<500 else 0.5
cols=k if W<500 else 3; rows=(k+cols-1)//cols
tw,th=int(W*sc),int(H*sc); M=Image.new('RGB',(tw*cols,th*rows),(0,0,0))
for i,t in enumerate(tiles): M.paste(t.resize((tw,th)),((i%cols)*tw,(i//cols)*th))
buf=io.BytesIO(); M.save(buf,'JPEG',quality=55); s=base64.b64encode(buf.getvalue()).decode()
for i in range(0,len(s),3000): print('B64 %s %d %s'%(tag,i//3000,s[i:i+3000]),flush=True)
print('B64END',tag,len(s),flush=True)
