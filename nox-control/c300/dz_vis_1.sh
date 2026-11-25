cd /tmp && python3 - <<'P'
import json,base64,io,time,urllib.request
from PIL import Image,ImageDraw
im=Image.new("RGB",(512,512),"white");d=ImageDraw.Draw(im)
d.rectangle([150,250,360,430],outline="black",width=5);d.polygon([(130,250),(255,140),(380,250)],outline="black",width=5)
d.rectangle([230,330,280,430],outline="black",width=4);d.rectangle([170,280,215,325],outline="black",width=3)
d.ellipse([400,60,460,120],outline="black",width=4)
b=io.BytesIO();im.save(b,"PNG");u="data:image/png;base64,"+base64.b64encode(b.getvalue()).decode()
def post(path,obj,t=240):
    r=urllib.request.Request("http://127.0.0.1:8091"+path,data=json.dumps(obj).encode(),headers={"Content-Type":"application/json"})
    try:
        x=urllib.request.urlopen(r,timeout=t);return x.status,x.read().decode()
    except urllib.error.HTTPError as e: return e.code,e.read().decode()
print("OUT: glm",post("/glm/v1/chat/completions",{"messages":[{"role":"user","content":"hi"}],"max_tokens":5})[0])
P=("Это набросок 512x512. Перерисуй его как чистый векторный SVG viewBox 0 0 512 512. "
"Верни ТОЛЬКО SVG без пояснений. Каждая деталь отдельным элементом с id (house-wall, roof, door, window, sun) в группах <g id=...>. Цвета плоские, компактно.")
t=time.time();c,txt=post("/vision/describe",{"image":u,"prompt":P});print("OUT: vision",c,round(time.time()-t),"s",len(txt))
print("OUT:",txt[:1500].replace("\n"," "))
P
