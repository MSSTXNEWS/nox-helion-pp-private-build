S=/workspace/nox/web/site
cd $S
cd /workspace/nox/web/site
python3 - <<'P'
import re
s=open('atlas.html',encoding='utf-8').read(); m=open('atlas-s1.main.html',encoding='utf-8').read()
s=re.sub(r'<main.*?</main>',lambda x:m,s,count=1,flags=re.S); open('atlas.html','w',encoding='utf-8').write(s); print('atlas swap ok')
P
