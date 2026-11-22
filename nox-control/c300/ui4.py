import re, time, shutil
W="/root/nox/web/"; ts=str(int(time.time()))
css=("/* c300 compact v2 */(function(){var s=document.createElement('style');s.textContent="
 "'.msgs .m{margin:3px 0 !important}.msgs .m .bubble{padding:7px 12px !important;line-height:1.38 !important}"
 ".msgs .m .bubble p{margin:0 0 .3em !important}.msgs .m .bubble p:last-child{margin-bottom:0 !important}"
 ".msgs .m .meta{margin:2px 0 !important;font-size:10px}.msgs .m .acts{margin-top:2px !important}"
 ".msgs .m .acts .seg button{width:26px !important;height:24px !important}.msgs{gap:2px !important}';"
 "document.head.appendChild(s)})();\n")
p=W+"nox_mode.js"; s=open(p).read()
if "c300 compact v2" not in s: shutil.copy(p,p+".b"+ts); open(p,"a").write("\n"+css)
h=W+"chat.html"; t=open(h).read(); shutil.copy(h,h+".b"+ts)
if "nox_mode.js" in t: t=re.sub(r'nox_mode\.js\?v=\d+','nox_mode.js?v='+ts,t)
else: t=t.replace("</body>",'<script src="./nox_mode.js?v=%s"></script>\n</body>'%ts,1)
open(h,"w").write(t); print("tag", t.count("nox_mode.js"))
