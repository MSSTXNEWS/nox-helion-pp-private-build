echo "C300: v_gw_1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
A=/workspace/nox/advisors; S=/workspace/nox/state; mkdir -p $A $S/secrets
for f in v_gw_gateway.py v_gw_register.py; do
  [ -f $A/$f ] && cp -n $A/$f $A/$f.bak_v_1
  curl -fsSL "$R/$f?$(date +%s)" -o $A/$f.new && mv $A/$f.new $A/$f || echo FAIL $f
done
mv -f $A/v_gw_gateway.py $A/gateway.py; mv -f $A/v_gw_register.py $A/register.py
E=$S/secrets/advisors.env
if [ ! -f $E ]; then cat > $E <<'X'
# Ключи внешних советников (бесплатные тарифы). Впишите значение после '=' - шлюз подхватит сразу, без перезапуска.
OPENROUTER_API_KEY=
GITHUB_MODELS_TOKEN=
GROQ_API_KEY=
CEREBRAS_API_KEY=
GEMINI_API_KEY=
MISTRAL_API_KEY=
LLM7_API_KEY=
POLLINATIONS_API_KEY=
X
fi
chmod 600 $E; chmod 700 $S/secrets
PORT=8793; ss -ltn | grep -q ":$PORT " && echo "port $PORT busy: $(pgrep -f advisors/gateway.py)"
# реестр сервисов (с бэкапом)
RJ=/workspace/nox/web/pkg/server/svc_registry.json
python3 - <<P
import json,shutil,os
p='$RJ'
if not os.path.exists(p+'.bak_v_1'): shutil.copy(p,p+'.bak_v_1')
d=json.load(open(p)); d['advisors_gw']={'port':$PORT,'mode':'local','title':'Внешние советники (шлюз)','note':'OpenAI-совместимый /v1, 127.0.0.1'}
json.dump(d,open(p,'w'),ensure_ascii=False,indent=2); print('registered')
P
# автозапуск
SX=/workspace/nox/svc/start_extra.sh
[ -f $SX.bak_v_1 ] || cp $SX $SX.bak_v_1
echo "--- start_extra before"; head -c 1500 $SX; echo; ls /workspace/nox/state | head -30; df -BG /workspace | tail -1
python3 - <<P
p='$SX'; s=open(p).read()
s=s.replace('cd /workspace/nox/advisors && nohup setsid python3 gateway.py','nohup setsid python3 /workspace/nox/advisors/gateway.py'); open(p,'w').write(s)
if 'advisors/gateway.py' not in s:
    ln='\n# v: внешние советники\npgrep -f advisors/gateway.py >/dev/null || (nohup setsid python3 /workspace/nox/advisors/gateway.py >/workspace/nox/svc/logs/advisors.log 2>&1 </dev/null &)\n'
    L=s.rstrip('\n').split('\n')
    if L and L[-1].split()[:1] in (['wait'],['exec']): L.insert(len(L)-1, ln); s='\n'.join(L)+'\n'
    else: s=s.rstrip('\n')+'\n'+ln
    open(p,'w').write(s)
P
tail -5 $SX
kill $(pgrep -f 'python3 gateway.py' | while read p; do [ "$(readlink /proc/$p/cwd)" = /workspace/nox/advisors ] && echo $p; done) 2>/dev/null; pkill -f advisors/gateway.py; sleep 1
setsid nohup python3 $A/gateway.py >/workspace/nox/svc/logs/advisors.log 2>&1 </dev/null &
sleep 3; curl -s -m5 127.0.0.1:$PORT/health; echo
setsid nohup python3 $A/register.py >$A/register.log 2>&1 </dev/null &
sleep 45; tail -15 $A/register.log
echo END
