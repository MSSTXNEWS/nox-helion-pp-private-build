echo "C300: tr_stop1"
N=/workspace/nox; A=$N/agent/autotrain; OUT=$N/agent/out; D=$N/ops/dpo
date -u
mkdir -p $N/state/p3 $D
# 1) бэкап и патч autotrain.sh (новый inode: работающий bash не затронут)
cp -n $A/autotrain.sh $A/autotrain.sh.bak_tr_20261126
python3 - <<'PY'
p="/workspace/nox/agent/autotrain/autotrain.sh"
s=open(p,encoding="utf-8").read()
if "char_only" in s: print("уже пропатчен")
else:
    key='  PHASE=""; TRAIN_ROWS=""; TRAIN_SHA=""\n'
    assert s.count(key)==1
    blk=('  if [ -f $N/state/p3/char_only ]; then  # TR_CHAR_ONLY 26.11: knowledge/SFT на тех же данных отключены, учим только характер (DPO/персона, 50 шагов)\n'
         '    log "режим характера: knowledge отключён, DPO-цикл"; bash $N/ops/dpo/char_cycle.sh >> $OUT/char_cycle.log 2>&1\n'
         '    sleep 300; continue\n  fi\n')
    s=s.replace(key,blk+key)
    open(p+".new","w",encoding="utf-8").write(s)
    import os; os.chmod(p+".new",0o775); os.replace(p+".new",p); print("пропатчен")
PY
bash -n $A/autotrain.sh && echo "синтаксис ok"
# заглушка цикла характера (реальная версия заменит файл)
[ -f $D/char_cycle.sh ] || printf '#!/bin/bash\necho "$(date -u +%%T) char_cycle: заглушка, задач нет"\n' > $D/char_cycle.sh
chmod +x $D/char_cycle.sh
echo "режим характера включён 26.11 (TR): knowledge-цикл на неизменных данных отключён; откат: rm state/p3/char_only и вернуть autotrain.sh.bak_tr_20261126" > $N/state/p3/char_only
# 2) остановить холостой раунд r040 и перезапустить контроллер
echo "== до"; ps -eo pid,ppid,etimes,args | grep -E "autotrain.sh|distill_v2.py train|ckpt_guard" | grep -v grep | cut -c1-150
ls $A/rounds | tail -2; tail -3 $A/rounds/r040/train.log | cut -c1-200
kill 186699 2>/dev/null; sleep 1
pkill -f "distill_v2.py train"; pkill -f "agent/ckpt_guard.py"; sleep 5
pkill -f "agent/autotrain/autotrain.sh"; sleep 3
echo "== после kill"; ps -eo pid,ppid,args | grep -E "autotrain.sh|distill_v2.py train|ckpt_guard" | grep -v grep | cut -c1-150
nvidia-smi --query-gpu=memory.used --format=csv,noheader
setsid -f bash $A/autotrain.sh >/dev/null 2>&1 </dev/null
sleep 20
echo "== новый контроллер"; ps -eo pid,ppid,args | grep -E "autotrain.sh" | grep -v grep | cut -c1-120
tail -4 $OUT/autotrain.log | cut -c1-220; tail -3 $OUT/char_cycle.log 2>/dev/null
# 3) разведка готовых наборов и моделей (HF API с сервера), только метаданные
python3 - <<'PY'
import json,urllib.request,urllib.parse
def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"nox-disc/1"}),timeout=25).read())
seen={}
for q,extra in [("prompt injection",""),("prompt-injection",""),("sycophancy",""),("dpo russian",""),("preference russian",""),("russian instruct",""),("anti sycophancy",""),("hallucination refusal dpo",""),("persona identity dpo","")]:
    try: d=get("https://huggingface.co/api/datasets?"+urllib.parse.urlencode({"search":q,"limit":25,"sort":"downloads","direction":-1,"full":"true"}))
    except Exception as e: print("err",q,repr(e)[:80]); continue
    for x in d:
        tg=x.get("tags",[]); lic=[t[8:] for t in tg if t.startswith("license:")]
        lang=[t[9:] for t in tg if t.startswith("language:")]
        seen[x["id"]]=(x.get("downloads"),lic,lang[:5])
bad=lambda l: (not l) or any("nc" in a or a in("other","unknown","llama2","llama3","gemma") for a in l)
print("== наборы (не NC), id | downloads | license | lang")
for k,(dl,l,la) in sorted(seen.items(),key=lambda kv:-(kv[1][0] or 0)):
    if not bad(l): print(k,dl,l,la)
print("== (отброшены NC/без лицензии):",[k for k,(dl,l,la) in seen.items() if bad(l)][:40])
PY
echo END
