#!/bin/bash
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300; S=/workspace/nox/web/site; X=$S/vendor/nox-x
for f in photo.html nox-photo.js nox-dock-wow.js; do curl -fsSL $R/$f -o $S/$f; done; echo "files ok"
if [ ! -f $X/minipaint/index.html ]; then cd /tmp && rm -rf mp && mkdir mp && cd mp && curl -fsSL -o mp.zip https://codeload.github.com/viliusle/miniPaint/zip/refs/heads/master && unzip -q mp.zip && D=$(ls -d miniPaint-*) && mkdir -p $X/minipaint && cp -r $D/index.html $D/dist $D/images $X/minipaint/ 2>/dev/null; cp -r $D/src $X/minipaint/ 2>/dev/null; du -sh $X/minipaint; ls $X/minipaint; cd /tmp && rm -rf mp; fi
python3 - <<'P'
import json
p="/workspace/nox/web/site/nav.json"; d=json.load(open(p))
for g in d["groups"]:
    if g["group"]=="ТВОРЧЕСТВО" and not any(i["file"]=="photo.html" for i in g["items"]):
        g["items"].insert(0,{"file":"photo.html","title":"NOX HELION · ФОТОСТУДИЯ","soon":False}); print("nav: photo added")
json.dump(d,open(p,"w"),ensure_ascii=False,indent=1)
P
curl -fsSL $R/wr.py -o /tmp/wr.py && python3 /tmp/wr.py && bash /workspace/nox/web/pkg/server/run_web.sh restart 2>&1 | tail -1
for u in /web/photo.html /web/vendor/nox-x/minipaint/index.html /img/health; do echo "$u $(curl -s -m8 -o /tmp/u.b -w %{http_code} 127.0.0.1:8091$u) $(head -c 120 /tmp/u.b | tr '\n' ' ')"; done
cat > /tmp/pt.py <<'P'
import asyncio, base64
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-unsafe-swiftshader"]); pg=await b.new_page(viewport={"width":1400,"height":900}); errs=[]
        pg.on("pageerror", lambda e: errs.append(str(e)[:140]))
        await pg.goto("http://127.0.0.1:8091/web/photo.html"); await pg.wait_for_timeout(6000)
        api=await pg.evaluate("(()=>{const w=document.getElementById('mp').contentWindow;return {layers:!!(w.Layers&&w.Layers.insert),conv:!!(w.Layers&&w.Layers.convert_layers_to_canvas),cfg:!!w.config, W:w.config&&w.config.WIDTH}})()")
        ok=await pg.evaluate("""(async()=>{const c=document.createElement('canvas');c.width=200;c.height=120;const x=c.getContext('2d');x.fillStyle='#e33';x.fillRect(0,0,200,120);x.fillStyle='#fff';x.font='40px sans-serif';x.fillText('NOX',50,75);
          const w=document.getElementById('mp').contentWindow; await new Promise(r=>{const i=new Image();i.onload=()=>{w.Layers.insert({name:'t',type:'image',data:i,width:200,height:120,width_original:200,height_original:120});r()};i.src=c.toDataURL()});
          const r=await fetch('/vision/describe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:c.toDataURL('image/jpeg'),prompt:'Что написано на картинке и какой фон? Одной фразой.'})}); return [r.status,(await r.json())]})()""")
        print("miniPaint api", api); print("vision", str(ok)[:220]); print("errs", errs[:3]); await b.close()
asyncio.run(main())
P
timeout 200 /workspace/nox/venv/bin/python /tmp/pt.py 2>&1 | tail -4
