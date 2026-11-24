set -e; cd /workspace/nox/web/site
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL "$RAW/qa_ctl.py" -o /workspace/nox/qa_ctl.py; curl -fsSL "$RAW/qa.html" -o qa.html
# fix manual overlay & filerobot tabs
grep -q 'nxManual\[hidden\]' nox-manual.js || sed -i "1i try{document.head.insertAdjacentHTML('beforeend','<style>#nxManual[hidden],.nxm[hidden]{display:none!important}</style>')}catch(e){}" nox-manual.js
grep -q FIE_tab photo.html || python3 -c "
p='photo.html';s=open(p).read();c='<style>#fie .FIE_tab{background:rgba(255,255,255,.04)!important;border:1px solid rgba(255,255,255,.06)!important}#fie .FIE_tab *{color:#cbb9a6!important}#fie .FIE_tab[aria-selected=true]{background:rgba(255,90,60,.18)!important}</style>'
open(p,'w').write(s.replace('</head>',c+'</head>',1))"
python3 - <<'P'
import json;p='nav.json';d=json.load(open(p));s=json.dumps(d,ensure_ascii=False)
if 'qa.html' not in s:
  def add(o):
    if isinstance(o,list):
      for x in o:
        if isinstance(x,dict) and 'tools.html' in json.dumps(x): 
          pass
    return o
  print('nav keys',list(d)[:8] if isinstance(d,dict) else type(d))
P
cat > /workspace/nox/qa_loop.sh <<'L'
#!/bin/bash
while true; do flock -n /tmp/qa.lock nice -n 15 /workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py >> /workspace/nox/agent/out/qa.log 2>&1; sleep 900; done
L
chmod +x /workspace/nox/qa_loop.sh
grep -q qa_loop /root/onstart.sh || echo 'nohup /workspace/nox/qa_loop.sh >/dev/null 2>&1 &' >> /root/onstart.sh
/workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py --pin
pkill -f qa_loop.sh || true
timeout 900 /workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py | head -90
nohup setsid /workspace/nox/qa_loop.sh >/dev/null 2>&1 < /dev/null &
echo loop started
