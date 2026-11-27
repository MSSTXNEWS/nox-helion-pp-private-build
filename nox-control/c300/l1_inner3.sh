echo "K1: l1_inner3"
python3 - <<'P'
import json,time,urllib.request
for mt in (200,):
  t0=time.time()
  b={"model":"x","messages":[{"role":"user","content":"Одной фразой: о чём ты думаешь сейчас?"}],"max_tokens":mt,"id_slot":1}
  d=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8105/v1/chat/completions",data=json.dumps(b).encode(),headers={"Content-Type":"application/json"}),timeout=120))
  m=d["choices"][0]["message"]; print("8105 sec",round(time.time()-t0,1),"content_len",len(m.get("content") or ""),"reasoning_len",len(m.get("reasoning_content") or ""),"finish",d["choices"][0]["finish_reason"])
P
# журнал внутреннего цикла: сколько отказов за последний час
cd /workspace/nox; for f in $(grep -rl "мыслей не отвечает" state logs 2>/dev/null | head -3); do echo "file=$(basename $f) total=$(grep -c 'мыслей не отвечает' $f) last_hour=$(awk -v t=$(date -d '1 hour ago' +%s) 'END{}' $f; find $f -mmin -60 | wc -l)"; done
pgrep -af "nox_inner_loop" | wc -l
