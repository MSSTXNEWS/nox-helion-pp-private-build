S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
python3 - <<'P'
import json
r=json.load(open('qa/registry.json')); c=r.get('commands',{})
print(len(c))
for k,v in list(c.items())[:70]: print(k,'|',(v.get('desc') or v.get('title') or v.get('name') or '')[:50],'|',v.get('danger',''),'|',v.get('kind',v.get('type','')),'|',str(v.get('run',v.get('api',v.get('action',''))))[:50])
P
python3 - <<'P'
s=open('nox-cmd.js',encoding='utf-8').read(); i=s.find('window.NOXcmd ='); print(s[i:i+1800])
P
grep -o "cx-right[^;]\{0,10\}" nox-chat-tg.js | head -2; python3 - <<'P'
s=open('nox-chat-tg.js',encoding='utf-8').read()
import re
for m in re.finditer(r"cx-right",s):
    print(s[max(0,m.start()-120):m.start()+300].replace('\n',' ')); print('---'); break
P
