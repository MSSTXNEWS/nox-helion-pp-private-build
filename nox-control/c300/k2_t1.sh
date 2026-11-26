echo "C300: k2_t1"
N=/workspace/nox; ST=$N/state
tail -2 $ST/k2_job2.log | cut -c1-200; tail -3 $ST/k2_r8105.log | cut -c1-200
echo "--- 8105 quick test (max_tokens 40)"
for q in "Скажи слово: привет" "2+2="; do s=$(date +%s); r=$(curl -s -m 100 127.0.0.1:8105/v1/chat/completions -H 'Content-Type: application/json' -d "{\"model\":\"x\",\"messages\":[{\"role\":\"user\",\"content\":\"$q\"}],\"max_tokens\":40}" | python3 -c "import sys,json;d=json.load(sys.stdin);m=d['choices'][0]['message'];t=d.get('timings',{});print('ok',len((m.get('content') or '')+(m.get('reasoning_content') or '')),'chars; pred/s',round(t.get('predicted_per_second',0),1),'prompt/s',round(t.get('prompt_per_second',0),1))" 2>&1 | tail -1); echo "$q -> $r ($(( $(date +%s)-s ))s)"; done
echo "--- unpaused chat ref"; python3 /tmp/k2_turn.py "Привет, расскажи шутку" ref 2>&1 | tail -1
ps -o pid,stat,ni,etimes -p $(pgrep -f "port 8105 " | head -1) | tail -1
