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
b=s[s.find('<body'):]
out=[]
for m in re.finditer(r'<(/?)(div|section|aside|nav|header|main|form|ul|button|label|textarea|input)\b([^>]*)>',b):
    if m.group(1): continue
    a=m.group(3); i=re.search(r'id="([^"]*)"',a); c=re.search(r'class="([^"]*)"',a)
    out.append(m.group(2)+('#'+i.group(1) if i else '')+('.'+c.group(1).replace(' ','.') if c else ''))
print(len(b)); print(' | '.join(out)[:5500])
P
grep -n "grid-template-columns" nox-chat-tg.css | cut -c1-260 | head -8
ls qa/registry.json && head -c 600 qa/registry.json; grep -o "NOXcmd[.a-zA-Z]*" nox-cmd.js | sort -u | head; curl -s -m5 -o /dev/null -w "cmd %{http_code}\n" http://127.0.0.1:8091/api/cmd
