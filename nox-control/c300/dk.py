import os, re, shutil, time, urllib.request, json, tarfile, io
S="/workspace/nox/web/site"; V=S+"/vendor/nox-x/fx2"; os.makedirs(V, exist_ok=True)
def npm(pkg, files, ver="latest"):
    m=json.load(urllib.request.urlopen("https://registry.npmjs.org/%s/%s"%(pkg,ver),timeout=60)); t=tarfile.open(fileobj=io.BytesIO(urllib.request.urlopen(m["dist"]["tarball"],timeout=120).read()))
    for x in t.getmembers():
        p=x.name.split("/",1)[1]
        if p in files: open(os.path.join(V,os.path.basename(p)),"wb").write(t.extractfile(x).read())
    print("OK",pkg,m["version"])
for a in (("vanilla-tilt",["dist/vanilla-tilt.min.js"]),("hover.css",["css/hover-min.css"]),("splitting",["dist/splitting.min.js","dist/splitting.css","dist/splitting-cells.css"])):
    try: npm(*a)
    except Exception as e: print("FAIL",a[0],e)
ts=time.strftime("%H%M%S")
n=S+"/nox-nav.js"; s=open(n).read()
if "nox-dock-wow.js" not in s:
    shutil.copy(n,n+".bak_c300_"+ts); open(n,"a").write("\n/* c300: вау-навигация (категории снизу, система сверху) */\nimport('./nox-dock-wow.js').catch((e) => console.warn('dock-wow:', e.message));\n"); print("nav hooked")
tag='<script src="./nox-dock-wow.js" defer></script>'
for f in os.listdir(S):
    if f.endswith(".html") and f!="tv.html":
        p=os.path.join(S,f); h=open(p,encoding="utf-8",errors="ignore").read()
        if "nox-nav.js" not in h and "nox-dock-wow.js" not in h and "</body>" in h:
            shutil.copy(p,p+".bak_c300_"+ts); open(p,"w",encoding="utf-8").write(h.replace("</body>",tag+"\n</body>",1)); print("tag ->",f)
