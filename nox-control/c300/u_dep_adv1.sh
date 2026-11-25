echo "C300: u_dep_adv1"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
R=/workspace/nox/web/pkg/server/svc_registry.json
echo "== 1 registry"; ls -la $R; head -c 500 $R; echo
cp $R $R.bak_u_$TS
python3 - <<'PYX'
import json
R='/workspace/nox/web/pkg/server/svc_registry.json';d=json.load(open(R,encoding='utf-8'))
ex=next(iter(d.values())) if d else {}
print('example',ex)
for k,p in (('advgw',8793),('agents',8810)):
    if k not in d: d[k]={'port':p,'mode':'strip','title':'NOX '+k}
json.dump(d,open(R,'w',encoding='utf-8'),ensure_ascii=False,indent=1);print('keys',list(d)[:30])
PYX
sleep 2
for p in /svc/advgw/health /svc/advgw/v1/models /svc/agents/board; do echo "$p $(curl -s -m 8 -o /tmp/u_o.txt -w '%{http_code}' localhost:8091$p) $(head -c 200 /tmp/u_o.txt | tr '\n' ' ')"; done
echo "== 2 board shape"; curl -s -m 8 localhost:8091/svc/agents/board | head -c 1500; echo
ID=$(curl -s -m 8 localhost:8091/svc/agents/board | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin);
  def f(o):
    if isinstance(o,dict):
      for k in ('id','task_id'):
        if k in o and isinstance(o[k],(str,int)): return o[k]
      for v in o.values():
        r=f(v)
        if r: return r
    if isinstance(o,list):
      for v in o:
        r=f(v)
        if r: return r
  print(f(d) or '')
except Exception: print('')")
echo "card id=$ID"; [ -n "$ID" ] && curl -s -m 8 localhost:8091/svc/agents/task/$ID/card | head -c 900; echo
echo "== 3 draw.js senior -> /svc/advgw"
cp nox-k8-draw.js nox-k8-draw.js.bak_u3_$TS
python3 - <<'PYX'
f='nox-k8-draw.js';s=open(f,encoding='utf-8').read()
n=s.count("'/svc/advisors/v1/'+path")
s=s.replace("'/svc/advisors/v1/'+path","'/svc/advgw/v1/'+path")
# критика: improved_prompt и поля
o="return{score:sc!=null?sc:(m?parseFloat(m[1].replace(',','.')):null),errors:String(c.errors||c.issues||c.problems||'').slice(0,200),text:t.slice(0,300)}"
nw="return{score:sc!=null?sc:(m?parseFloat(m[1].replace(',','.')):null),errors:[].concat(c.issues||c.errors||[]).join('; ').slice(0,200),fixes:[].concat(c.fixes||[]).join('; ').slice(0,200),improved:c.improved_prompt||'',text:t.slice(0,300)}"
k=o in s
s=s.replace(o,nw)
# цикл: gen -> critique -> improved_prompt -> gen (до 2 раз)
o2="const su=await senior.gen(prompt,sig);if(su){const c2=await senior.critic(su,prompt,sig);"
n2="let sp=prompt,su=null,c2=null;for(let q=0;q<2&&!(sig&&sig.aborted);q++){su=await senior.gen(sp,sig);if(!su)break;c2=await senior.critic(su,prompt,sig);if(!c2||c2.score==null||c2.score>=8||!c2.improved)break;sp=c2.improved}if(su){"
k2=o2 in s
s=s.replace(o2,n2)
open(f,'w',encoding='utf-8').write(s);print('route',n,'critic',k,'loop',k2)
PYX
node --check nox-k8-draw.js && echo SYNTAX_OK || { cp nox-k8-draw.js.bak_u3_$TS nox-k8-draw.js; echo ROLLBACK; }
sed -i 's#nox-k8-draw.js?v=u2#nox-k8-draw.js?v=u3#' creative.html
echo "== 4 живой тест шлюза через прокси"
timeout 100 curl -s -m 95 -X POST localhost:8091/svc/advgw/v1/images/generations -H 'Content-Type: application/json' -d '{"prompt":"a red apple on a wooden table, photo","model":"auto","size":"512x512","response_format":"b64_json"}' | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin);print('GEN keys',list(d), d.get('model'), (d.get('data') or [{}])[0].get('path'), len((d.get('data') or [{}])[0].get('b64_json') or ''), d.get('error'))
except Exception as e: print('GEN parse',e)"
echo "== 5 creative QA"
cat > /tmp/u_c3.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for w,h in((1440,900),(390,844)):
      c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
      await c.goto('http://127.0.0.1:8091/web/creative.html',wait_until='domcontentloaded');await c.wait_for_function('window.K8draw',timeout=15000);await c.wait_for_timeout(1500)
      print('QA',w,await c.evaluate("typeof K8draw.senior.critic+'/'+K8draw.presets.length"),errs[:2],flush=True);await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 60 $PY /tmp/u_c3.py > /tmp/u_c3.out; cat /tmp/u_c3.out; grep -q "errs\|\['" /tmp/u_c3.out | true; grep -q "\[\]" /tmp/u_c3.out || { cp nox-k8-draw.js.bak_u3_$TS nox-k8-draw.js; echo ROLLBACK_QA; }
echo "u_dep_adv1 done"
