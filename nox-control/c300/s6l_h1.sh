echo "K1: s6l_h1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; S=$N/state/s6; mkdir -p $S
echo "train=$(pgrep -f 'train_dpo.py' | wc -l) lock=$([ -d /home/claude/brain/BODY_LOCK ] && echo yes || echo no) llama=$(pgrep -f llama-server | wc -l)"
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader
for t in "Привет!" ; do python3 -I - <<'PY'
import json,urllib.request,time
t0=time.time(); txt=""
r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-pers-probe","message":"Привет!","mode":"fast","user_id":"qa_exam"}).encode(),{"Content-Type":"application/json"}),timeout=120)
for ln in r:
    try: o=json.loads(ln)
    except Exception: continue
    if o.get("t")=="delta": txt+=str(o.get("text") or "")
    if o.get("t") in("done","error","stopped"): break
print("probe sec",round(time.time()-t0,1),"chars",len(txt),"busy_fallback","модель занята" in txt)
PY
done
rm -f $S/exam_live.keep
setsid nohup nice -n 5 python3 -I $N/mods/persona_exam.py --chat http://127.0.0.1:18091 --keep $S/exam_live.keep --out $S/persona_exam_live.json > $S/persona_exam_live.log 2>&1 < /dev/null &
echo started; echo END
