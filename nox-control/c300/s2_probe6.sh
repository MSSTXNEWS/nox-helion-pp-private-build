#!/bin/bash
sed -n 28,60p /workspace/nox/qa_audit.py | cut -c1-200
for p in /web/cinema.html /cinema.html /web/ ; do printf "$p "; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8091$p; done
python3 - <<'PY'
import re,urllib.request,urllib.parse
UA={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) Chrome/120'}
for q in ['Мосфильм официальный канал','Ленфильм официальный канал','Союзмультфильм официальный','Советские мультфильмы канал']:
    u='https://www.youtube.com/results?search_query='+urllib.parse.quote(q)+'&sp=EgIQAg%3D%3D'
    try:
        p=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=15).read().decode('utf8','ignore')
        r=re.findall(r'"channelRenderer":\{"channelId":"(UC[\w-]{22})".{0,1500}?"text":"([^"]+)"',p,re.S)
        print(q,[(a,b) for a,b in r[:5]])
    except Exception as e: print(q,'ERR',e)
PY
