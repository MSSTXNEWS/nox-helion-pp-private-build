import sys,base64,io
from playwright.sync_api import sync_playwright
# usage: shot.py name url [url2 name2 ...] -> prints B64
args=sys.argv[1:]
pairs=[(args[i],args[i+1]) for i in range(0,len(args),2)]
from PIL import Image
with sync_playwright() as p:
    b=p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist"])
    for name,url in pairs:
        for vp,(w,h) in (("desk",(1440,900)),("mob",(390,844))):
            pg=b.new_page(viewport={"width":w,"height":h}); 
            try: pg.goto(url,wait_until="load",timeout=40000)
            except Exception as e: print("goto err",e)
            pg.wait_for_timeout(5000)
            png=pg.screenshot()
            im=Image.open(io.BytesIO(png)).convert("RGB"); bio=io.BytesIO(); im.save(bio,"JPEG",quality=38)
            s=base64.b64encode(bio.getvalue()).decode()
            print(f"B64_{name}_{vp}_BEGIN")
            for i in range(0,len(s),900): print(s[i:i+900])
            print(f"B64_{name}_{vp}_END")
            pg.close()
    b.close()
