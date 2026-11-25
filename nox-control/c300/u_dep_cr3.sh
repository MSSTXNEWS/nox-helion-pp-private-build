echo "C300: u_dep_cr3"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
echo "== 1 kill audits"; pgrep -af "qa_audit|u_audit" | cut -c1-120
pkill -f u_audit3.sh; pkill -f u_audit4.sh; pkill -f "qa_audit.py"; sleep 2; pgrep -af "qa_audit" | head -2; echo "after kill: $(pgrep -f qa_audit | wc -l)"
for f in nox-dz-creative.js nox-s2-creative.js; do cp $f $f.bak_u7_$TS; done
python3 - <<'PYX'
f='nox-dz-creative.js';s=open(f,encoding='utf-8').read()
if 'U_BADGE' not in s:
    a=s.index('function genCheck0(){');b=s.index('\n',a)
    s=s[:a]+"/* U_BADGE: без запросов к /img/generate; статус из кэша реальных попыток, иначе проверка шлюза советников */\nfunction genCheck0(){return fetch('/svc/advgw/health',{cache:'no-store'}).then(function(r){window.__advOk=r.ok;return{code:503,j:{}}}).catch(function(){window.__advOk=false;return{code:0,j:{}}})}"+s[b:]
    s=s.replace("b.textContent=off?'Генератор: недоступно':'Генератор: включён'","b.textContent=off?(window.__advOk?'Через старшего советника':'Генератор: недоступно'):'Генератор: включён'",1)
    s=s.replace("n.textContent=off?'Недоступно, включится после обучения (проверка раз в минуту). Пока работают vision-функции выше.':","n.textContent=off?(window.__advOk?'Локальная генерация занята обучением: рисует старший советник (вкладка «Генерация NOX» и студия). Локальная включится после обучения.':'Недоступно, включится после обучения. Пока работают vision-функции выше.'):",1)
    s=s.replace("if(v&&Date.now()-t<600000)return Promise.resolve({code:+v,j:{}});return genCheck0()","if(v&&+v===200&&Date.now()-t<600000)return Promise.resolve({code:200,j:{}});return genCheck0()",1)
    open(f,'w',encoding='utf-8').write(s);print('dz patched')
f='nox-s2-creative.js';s=open(f,encoding='utf-8').read()
o="catch(_){}})};\n  (window.K8draw"
if o in s and 'Через старшего' not in s:
    s=s.replace(o,"catch(_){};if(window.K8draw)return K8draw.gen(full).then(function(du){if(du){addImg(du,'Старший советник');$('#gSt').textContent='Готово (старший советник)';$('#crSt').textContent='Через старшего советника';$('#crSt').className='s2-chip ok'}})})};\n  (window.K8draw",1);open(f,'w',encoding='utf-8').write(s);print('s2 patched')
PYX
for f in nox-dz-creative.js nox-s2-creative.js; do node --check $f && echo "OK $f" || { cp $f.bak_u7_$TS $f; echo "ROLLBACK $f"; }; done
sed -i -E 's#(nox-s2-creative\.js)\?v=[A-Za-z0-9_]+#\1?v=u7#; s#(nox-dz-creative\.js)\?v=[A-Za-z0-9_]+#\1?v=u7#' creative.html
cat > /tmp/u_cr7.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    c=await b.new_page(viewport={'width':1440,'height':900});errs=[];gen=[]
    c.on('pageerror',lambda e:errs.append(str(e)[:100]));c.on('request',lambda r:gen.append(r.url[-30:]) if '/img/generate' in r.url else None)
    await c.goto('http://127.0.0.1:8091/web/creative.html',wait_until='domcontentloaded');await c.wait_for_timeout(7000)
    print('QA badge',await c.evaluate("(document.getElementById('bGen')||{}).textContent"),'img/generate requests',len(gen),errs[:2],flush=True)
    await b.close()
asyncio.run(m())
PEOF
timeout 60 $PY /tmp/u_cr7.py | tee /tmp/u_cr7.out
grep -E "^QA" /tmp/u_cr7.out | grep -q "Unexpected\|Error" && { for f in nox-dz-creative.js nox-s2-creative.js; do cp $f.bak_u7_$TS $f; done; echo ROLLBACK_ALL; } || echo QA_CLEAN
echo "== 2 clean audit (single, sequential)"
O=/workspace/nox/agent/out; rm -f $O/u_qab_*
cat > $O/u_audit5.sh <<'AEOF'
cd /workspace/nox/web/site; O=/workspace/nox/agent/out
for p in creative index settings; do /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html > $O/u_qab_$p.out 2>&1; python3 - $p <<'PY' >> $O/u_qab_prog.txt
import json,sys
d=json.load(open('/workspace/nox/web/site/qa/audit.json',encoding='utf-8'))[sys.argv[1]];print(sys.argv[1],d.get('ts'),'wow',d.get('wow'),'ARU',d.get('ARU'),'runs',d.get('vision_runs'),'fails',[f['item'][:34]+':'+str(f.get('detail'))[:60] for f in d.get('fails',[])])
PY
done; echo FIN >> $O/u_qab_prog.txt
AEOF
setsid nohup bash $O/u_audit5.sh >/dev/null 2>&1 < /dev/null &
sleep 2; echo "audit procs: $(pgrep -f qa_audit | wc -l)"; echo done
