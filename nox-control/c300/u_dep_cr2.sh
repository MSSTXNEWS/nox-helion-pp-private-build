echo "C300: u_dep_cr2"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
for f in nox-k8-draw.js nox-s2-creative.js nox-dz-creative.js; do cp $f $f.bak_u6_$TS; done
python3 - <<'PYX'
import re
# 1) K8draw: localOk по общему кэшу, пометка отказа
f='nox-k8-draw.js';s=open(f,encoding='utf-8').read()
a=s.index('/* U_LOCALOK */');b=s.index(' const senior={')
s=s[:a]+"/* U_LOCALOK2 */ async function localOk(){try{const v=localStorage.getItem('nox.img.chk.v'),t=+localStorage.getItem('nox.img.chk')||0;if(v&&Date.now()-t<600000)return +v===200||+v===202}catch(e){}return true}\n function markFail(c){try{localStorage.setItem('nox.img.chk',String(Date.now()));localStorage.setItem('nox.img.chk.v',String(c||503))}catch(e){}}\n"+s[b:]
s=s.replace("if(j&&j.error&&window.K8studio)K8studio.post(","if(j&&j.error)markFail(r.status);if(j&&j.error&&window.K8studio)K8studio.post(",1)
s=s.replace("window.K8draw={senior:senior,","window.K8draw={localOk:localOk,senior:senior,",1)
open(f,'w',encoding='utf-8').write(s)
# 2) dz genCheck: кэш 10 минут вместо запроса каждую минуту
f='nox-dz-creative.js';s=open(f,encoding='utf-8').read()
if 'genCheck0' not in s:
    s=s.replace("function genCheck(){return fetch(","function genCheck(){var t=+localStorage.getItem('nox.img.chk')||0,v=localStorage.getItem('nox.img.chk.v');if(v&&Date.now()-t<600000)return Promise.resolve({code:+v,j:{}});return genCheck0().then(function(x){try{localStorage.setItem('nox.img.chk',String(Date.now()));localStorage.setItem('nox.img.chk.v',String(x.code))}catch(e){}return x})}\nfunction genCheck0(){return fetch(",1)
    open(f,'w',encoding='utf-8').write(s)
# 3) s2 gen: при недоступном локальном — старший советник
f='nox-s2-creative.js';s=open(f,encoding='utf-8').read()
if '_L=function' not in s:
    o="  fetch('/img/generate',{method:'POST'"
    assert o in s
    s=s.replace(o,"  var _L=function(){return fetch('/img/generate',{method:'POST'",1)
    e="$('#crSt').className='s2-chip bad'});"
    i=s.index(e,s.index('var _L=function'))
    s=s[:i]+"$('#crSt').className='s2-chip bad';try{localStorage.setItem('nox.img.chk',String(Date.now()));localStorage.setItem('nox.img.chk.v','503')}catch(_){}})};\n  (window.K8draw&&K8draw.localOk?K8draw.localOk():Promise.resolve(true)).then(function(ok){if(ok)return _L();return K8draw.gen(full).then(function(du){if(du){addImg(du,'Старший советник');$('#gSt').textContent='Готово (старший советник)'}else _L()})});"+s[i+len(e):]
    open(f,'w',encoding='utf-8').write(s)
print('patched')
PYX
for f in nox-k8-draw.js nox-s2-creative.js nox-dz-creative.js; do node --check $f && echo "OK $f" || { cp $f.bak_u6_$TS $f; echo "ROLLBACK $f"; }; done
sed -i -E 's#(nox-k8-draw\.js|nox-s2-creative\.js|nox-dz-creative\.js)\?v=[A-Za-z0-9_]+#\1?v=u6#' creative.html
grep -o "nox-[a-z0-9-]*creative.js?v=[a-z0-9]*" creative.html | head
timeout 100 $PY /tmp/u_cr5.py | tee /tmp/u_cr6.out
grep -E "^QA" /tmp/u_cr6.out | grep -q "Unexpected\|Error\|EXC" && { for f in nox-k8-draw.js nox-s2-creative.js nox-dz-creative.js; do cp $f.bak_u6_$TS $f; done; echo ROLLBACK_ALL; } || echo QA_CLEAN
echo "== запуск ревизора по creative и index (фон)"
O=/workspace/nox/agent/out; pkill -f u_audit3.sh 2>/dev/null; pgrep -f qa_audit | head -2
cat > $O/u_audit4.sh <<'AEOF'
cd /workspace/nox/web/site; O=/workspace/nox/agent/out; rm -f $O/u_qab_*
for p in creative index settings; do /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html > $O/u_qab_$p.out 2>&1; python3 - $p <<'PY' >> $O/u_qab_prog.txt
import json,sys
d=json.load(open('/workspace/nox/web/site/qa/audit.json',encoding='utf-8'))[sys.argv[1]];print(sys.argv[1],d.get('ts'),'wow',d.get('wow'),'ARU',d.get('ARU'),'runs',d.get('vision_runs'),'fails',[f['item'][:30] for f in d.get('fails',[])])
PY
done; echo FIN >> $O/u_qab_prog.txt
AEOF
sleep 1; setsid nohup bash $O/u_audit4.sh >/dev/null 2>&1 < /dev/null &
echo done
