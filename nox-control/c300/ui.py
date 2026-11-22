import re, time, shutil
W="/root/nox/web/"; ts=time.strftime("%H%M%S")
p=W+"nox_mode.js"; s=open(p).read(); shutil.copy(p,p+".b"+ts)
old="dot(s.glm_up)+'Глубокий · GLM-5.3-Flash (~1,4 ток/с)</div>'"
new="(s.glm_busy?'<span class=\"dot\" style=\"background:#facc15\"></span>':dot(s.glm_up))+'Глубокий · GLM-5.3-Flash (~2,6 ток/с'+(s.glm_busy?', думает':'')+')</div>'"
print("widget", s.count(old)); s=s.replace(old,new); open(p,"w").write(s)
for f in ("nox-nav.js","nox-wow.js","nox-newchat.js"):
    p=W+f; s=open(p).read(); shutil.copy(p,p+".b"+ts); n=len(re.findall(r'GLM-5\.3(?!-Flash)',s)); s=re.sub(r'GLM-5\.3(?!-Flash)','GLM-5.3-Flash',s); open(p,"w").write(s); print(f,n)
h=W+"chat.html"; s=open(h).read(); s=re.sub(r'(nox_mode\.js\?v=)\d+',r'\g<1>'+str(int(time.time())),s); open(h,"w").write(s)
