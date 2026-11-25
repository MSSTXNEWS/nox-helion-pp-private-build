set -x
N=/workspace/nox; S=$N/web/site; P=$N/svc/pipeline; B=$P/ship1; O=$N/state/c_ship1.out; : > $O; exec >> $O 2>&1
echo "== 1. pipeline: модели без coder, русский"; cp -n $P/pipeline_svc.py $P/pipeline_svc.py.bak_c_ship; python3 $B/patch_fast.py && python3 -m py_compile $P/pipeline_svc.py && echo pc_ok || { cp $P/pipeline_svc.py.bak_c_ship $P/pipeline_svc.py; echo pc_rollback; }
pkill -f pipeline_svc.py; sleep 1; ( cd $P && nohup setsid $N/venv_living/bin/python pipeline_svc.py >$P/pipeline.log 2>&1 </dev/null & ); sleep 3; curl -s -m4 localhost:18217/health; echo
echo "== 2. race_s=3"; cp -n $N/state/persona.json $N/state/persona.json.bak_c_ship; python3 - <<'PY'
import json
p="/workspace/nox/state/persona.json"; d=json.load(open(p)); le=d.setdefault("living_engines",{}); le["race_s"]=3; le["clean"]=True; json.dump(d,open(p,"w"),ensure_ascii=False,indent=1); print(le)
PY
echo "== 3. site: clean-режим + dock"
cp -p $S/chat.html $S/chat.html.bak_c_ship; cp -p $S/nox-dock-wow.js $S/nox-dock-wow.js.bak_c_ship
cp $B/nox-chat-clean.js $B/nox-chat-clean.css $S/; python3 $B/patch_dock.py
grep -q nox-chat-clean.css $S/chat.html || sed -i 's#</head>#<link rel="stylesheet" href="./nox-chat-clean.css?v=1">\n<script defer src="./nox-chat-clean.js?v=1"></script>\n</head>#' $S/chat.html
grep -c nox-chat-clean $S/chat.html; grep -q nox-k8-meta $S/chat.html || sed -i 's#</head>#<script defer src="./nox-k8-meta.js"></script>\n</head>#' $S/chat.html; ls -la $S/nox-k8-meta.js
echo "== 4. 10 вопросов"
rm -f $N/state/c_ship1.rows; for q in "Привет!" "Столица Австралии?" "Скажи 2+2" "Назови три цвета радуги" "Что такое DNS? коротко" "Чем TCP отличается от UDP? коротко" "Посоветуй книгу" "Кто написал Войну и мир?" "Переведи hello на французский" "Сколько дней в феврале високосного года?"; do timeout 100 python3 $P/c_test.py "$q" cship$RANDOM 90 | tee -a $N/state/c_ship1.rows; done
python3 - <<'PY'
import re
n=e=0;fd=[]
for l in open("/workspace/nox/state/c_ship1.rows"):
    m=re.search(r"first_delta_s= ([\d.]+|None)",l)
    if m:
        n+=1
        if m.group(1)=="None": e+=1
        else: fd.append(float(m.group(1)))
print("ИТОГ: вопросов",n,"без текста",e,"max",max(fd) if fd else None,"<=8:",sum(1 for x in fd if x<=8))
PY
echo "== 5. скриншоты на сервере (1440, 390)"
$N/venv/bin/python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for W,H in ((1440,900),(390,844)):
        pg=b.new_page(viewport={"width":W,"height":H}); pg.goto("http://127.0.0.1:8091/web/chat.html"); pg.wait_for_timeout(6000)
        print(W,pg.evaluate("()=>({clean:document.body.classList.contains('cw-clean'),bar:!!document.querySelector('.cw-bar'),over:document.documentElement.scrollWidth>innerWidth})"))
        pg.screenshot(path="/workspace/nox/web/site/qa/c_clean_%d.png"%W)
    b.close()
PY
echo FINISHED
