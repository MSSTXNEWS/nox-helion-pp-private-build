echo "C300: restart8105"
N=/workspace/nox; ST=$N/state
cat > $ST/k2_r8105_job.sh <<'J'
#!/bin/bash
N=/workspace/nox; ST=$N/state; L=$ST/k2_r8105.log
NEW=$N/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf
OLD=$N/models/subcores/Qwen3-30B-A3B-Instruct-2507-GGUF/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf
log(){ echo "$(date -u +%T) $*" >> $L; }
[ "$(stat -c %s $NEW)" = 18556686752 ] || { log "size mismatch"; exit 1; }
[ "$(cut -d' ' -f1 $ST/k2_sha.txt)" = "$(grep -o '[0-9a-f]\{64\}' $ST/k2_etag.txt)" ] || { log "sha mismatch"; exit 1; }
log "file ok (size+sha)"
cp -n $N/stewards/orch_registry.json $N/stewards/orch_registry.json.bak_k2_8105
python3 - <<'P'
import json
f="/workspace/nox/stewards/orch_registry.json"; r=json.load(open(f))
js=r["jobs"] if isinstance(r,dict) and "jobs" in r else r
for j in js:
    if j.get("name")=="t_q30":
        c=j["cmd"]; c[c.index("-m")+1]="/workspace/nox/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf"
        c[c.index("-t")+1]="8"; j["nice"]=19; j["cpus"]="4-7,20-23"
json.dump(r,open(f,"w"),ensure_ascii=False,indent=1); print("registry updated")
P
touch $N/operators/PAUSE; touch $N/state/orch/pause/orq_q30; echo k2r8105 > $ST/skill_teacher_pause
for i in $(seq 450); do
  b=$(curl -s -m3 127.0.0.1:8105/slots | python3 -c "import json,sys;print(sum(1 for s in json.load(sys.stdin) if s.get('is_processing')))" 2>/dev/null)
  [ "$b" = "0" ] && break; sleep 2
done
log "slots free b=$b; stopping old"
old=$(pgrep -f "llama-server -m .*--port 8105 "); kill -CONT $old 2>/dev/null; kill $old; for i in $(seq 40); do kill -0 $old 2>/dev/null || break; sleep 0.5; done
python3 - <<'P' > /tmp/k2_cmd8105.txt
import json
r=json.load(open("/workspace/nox/stewards/orch_registry.json")); js=r["jobs"] if isinstance(r,dict) and "jobs" in r else r
j=[x for x in js if x.get("name")=="t_q30"][0]; print(" ".join(j["cmd"]))
P
cd $N && CUDA_VISIBLE_DEVICES="" setsid nohup taskset -c 4-7,20-23 nice -n 19 $(cat /tmp/k2_cmd8105.txt) >> $N/agent/out/llama8105_thinking.log 2>&1 < /dev/null &
for i in $(seq 240); do curl -sf -m2 127.0.0.1:8105/health >/dev/null && break; sleep 2; done
log "new 8105 health=$(curl -s -m2 127.0.0.1:8105/health)"
rm -f $N/operators/PAUSE $N/state/orch/pause/orq_q30; [ "$(cat $ST/skill_teacher_pause 2>/dev/null)" = k2r8105 ] && rm -f $ST/skill_teacher_pause
ok=0
for q in "Сколько будет 12*13?" "Назови столицу Франции." "Что такое DNS? Одним предложением."; do
  r=$(curl -s -m 240 127.0.0.1:8105/v1/chat/completions -H 'Content-Type: application/json' -d "{\"model\":\"x\",\"messages\":[{\"role\":\"user\",\"content\":\"$q\"}],\"max_tokens\":400}" | python3 -c "import sys,json;d=json.load(sys.stdin);m=d['choices'][0]['message'];print(len((m.get('content') or '')+(m.get('reasoning_content') or '')),'|',(m.get('content') or '')[:60].replace(chr(10),' '))" 2>&1 | tail -1)
  log "test '$q' -> $r"; case "$r" in [1-9]*) ok=$((ok+1));; esac
done
if [ $ok = 3 ]; then rm -f "$OLD" && log "OLD Instruct GGUF deleted"; else log "tests ok=$ok -> old file kept"; fi
df -BG /workspace | tail -1 >> $L; log "R8105 DONE"
J
chmod +x $ST/k2_r8105_job.sh; : > $ST/k2_r8105.log
env RUNNER_TRACKING_ID=k2r81 setsid -f bash $ST/k2_r8105_job.sh </dev/null >/dev/null 2>&1
sleep 8; cat $ST/k2_r8105.log; tail -3 $ST/k2_job2.log 2>&1
