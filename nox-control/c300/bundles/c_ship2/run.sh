set -x
N=/workspace/nox; S=$N/web/site; P=$N/svc/pipeline; B=$P/ship2; O=$N/state/c_ship2.out; : > $O; exec >> $O 2>&1
cp $B/nox-chat-clean.js $B/nox-chat-clean.css $S/; sed -i 's#nox-chat-clean.css?v=1#nox-chat-clean.css?v=2#;s#nox-chat-clean.js?v=1#nox-chat-clean.js?v=2#' $S/chat.html; grep -c "clean.*v=2" $S/chat.html
cp $P/pipeline_svc.py $P/pipeline_svc.py.bak_c_ship2; python3 $B/patch_fast2.py && python3 -m py_compile $P/pipeline_svc.py && echo pc_ok || { cp $P/pipeline_svc.py.bak_c_ship2 $P/pipeline_svc.py; echo rollback; }
pkill -f pipeline_svc.py; sleep 1; ( cd $P && nohup setsid $N/venv_living/bin/python pipeline_svc.py >$P/pipeline.log 2>&1 </dev/null & ); sleep 3; curl -s -m4 localhost:18217/test -d '{"q":"x"}' | cut -c1-300; echo
rm -f $N/state/c_ship2.rows; for q in "Привет!" "Столица Австралии?" "Скажи 2+2" "Что такое DNS? коротко" "Посоветуй книгу" "Кто написал Войну и мир?" "Переведи hello на французский" "Сколько дней в феврале високосного года?" "Назови три цвета радуги" "Чем TCP отличается от UDP?"; do timeout 100 python3 $P/c_test.py "$q" cship2$RANDOM 90 | tee -a $N/state/c_ship2.rows; done
python3 - <<'PY'
import re
n=e=0;fd=[]
for l in open("/workspace/nox/state/c_ship2.rows"):
    m=re.search(r"first_delta_s= ([\d.]+|None)",l)
    if m:
        n+=1
        if m.group(1)=="None": e+=1
        else: fd.append(float(m.group(1)))
print("ИТОГ: вопросов",n,"без текста",e,"max",max(fd) if fd else None,"<=8:",sum(1 for x in fd if x<=8))
PY
$N/venv/bin/python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for W,H in ((1440,900),(390,844)):
        pg=b.new_page(viewport={"width":W,"height":H}); pg.on("pageerror",lambda e:print("PERR",str(e)[:150])); pg.goto("http://127.0.0.1:8091/web/chat.html"); pg.wait_for_timeout(6000)
        print(W,pg.evaluate("()=>({clean:document.body.classList.contains('cw-clean'),bar:!!document.querySelector('.cw-bar'),hello:!!document.querySelector('.cw-hello.on'),over:document.documentElement.scrollWidth>innerWidth})"))
        pg.screenshot(path="/workspace/nox/web/site/qa/c_clean_%d.png"%W)
    b.close()
PY
echo FINISHED
