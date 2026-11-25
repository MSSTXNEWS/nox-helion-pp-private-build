S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
python3 - <<'P'
import re
s=open('chat.html',encoding='utf-8').read()
i=s.find('class="lv-bar"'); print('bar in html',i)
m=re.search(r'<form[^>]*>',s[:s.find('id="btnSend"')][::-1][:0]+s); 
j=s.find('id="btnSend"'); k=s.rfind('<form',0,j); print(s[k:k+300]); print(s[max(0,k-300):k])
P
grep -o "\.dock{[^}]*}" nox-chat-tg.css | head -3; grep -o "body.tg \.dock[^{]*{[^}]*}" nox-chat-tg.css | head -4
