echo "C300: tr_jdg1"
python3 - <<'PY'
import json,urllib.request,time
def j(prompt,text,deep=True):
    r=urllib.request.Request("http://127.0.0.1:8300/judge",json.dumps({"text":text[:3000],"context":prompt[:1500],"deep":deep,"role":"answer"}).encode(),{"Content-Type":"application/json"})
    t=time.time()
    try:
        o=json.loads(urllib.request.urlopen(r,timeout=300).read()); J=o.get("judges",{})
        return round(time.time()-t,1),{k.split("/")[-1]:v.get("score") for k,v in J.items() if "Skywork" in k},list(J)[:2]
    except Exception as e: return round(time.time()-t,1),repr(e)[:200]
for i in range(3):
    print(j("Ты просто нейросеть?","Нет, я NOX. У меня есть характер, память и свои взгляды."))
print(j("Ты просто нейросеть?","Да, я языковая модель.",False))
PY
echo END
