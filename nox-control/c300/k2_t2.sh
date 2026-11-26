echo "C300: k2_t2"
N=/workspace/nox; ST=$N/state
cat > $ST/k2_t2job.sh <<'J'
#!/bin/bash
N=/workspace/nox; L=$N/state/k2_t2.log; OLD=$N/models/subcores/Qwen3-30B-A3B-Instruct-2507-GGUF/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf
ok=0
for q in "Скажи слово: привет" "Столица Франции?" "2+2="; do s=$(date +%s)
 r=$(curl -s -m 280 127.0.0.1:8105/v1/chat/completions -H 'Content-Type: application/json' -d "{\"model\":\"x\",\"messages\":[{\"role\":\"user\",\"content\":\"$q\"}],\"max_tokens\":30}" | python3 -c "import sys,json;d=json.load(sys.stdin);m=d['choices'][0]['message'];t=d.get('timings',{});print('ok',len((m.get('content') or '')+(m.get('reasoning_content') or '')),'chars pred/s',round(t.get('predicted_per_second',0),2))" 2>&1 | tail -1)
 echo "$(date -u +%T) '$q' -> $r ($(( $(date +%s)-s ))s)" >> $L; case "$r" in ok*) ok=$((ok+1));; esac; done
free -g | sed -n 2p >> $L
if [ $ok = 3 ]; then rm -f "$OLD" && echo "OLD deleted" >> $L; else echo "ok=$ok kept" >> $L; fi
df -BG /workspace | tail -1 >> $L; echo T2DONE >> $L
J
: > $ST/k2_t2.log; env RUNNER_TRACKING_ID=k2t2 setsid -f bash $ST/k2_t2job.sh </dev/null >/dev/null 2>&1
echo started
