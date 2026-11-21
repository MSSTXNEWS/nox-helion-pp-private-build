#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-300; }
echo "== boot script"; sed -n 1,60p /root/nox/ops/nox_boot_ds41_8098.sh | grep -vE "^\s*#|^\s*$" | a | head -34
echo "== slots"; curl -s -m 10 http://127.0.0.1:8098/slots | python3 -c "import sys,json;d=json.load(sys.stdin);print([(s.get('id'),s.get('is_processing'),s.get('n_ctx')) for s in d])" 2>&1 | a
for i in 1 2; do
 S=$(date +%s.%N)
 curl -s -m 200 http://127.0.0.1:8098/completion -d '{"prompt":"Напиши три предложения о пользе чтения книг.","n_predict":48,"temperature":0,"cache_prompt":true,"stream":false}' | python3 -c "
import sys,json;d=json.load(sys.stdin);t=d.get('timings',{});print('run',$i,'prompt_n',t.get('prompt_n'),'prompt_ms',round(t.get('prompt_ms',0)),'pred_n',t.get('predicted_n'),'gen_tok_s',round(t.get('predicted_per_second',0),2),'stop',d.get('stop_type'))" 2>&1 | a
 echo "wall $(echo "$(date +%s.%N) - $S" | bc | cut -c1-6)s"
done
echo "== gpu during"; nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
uptime | a; free -g | awk 'NR==2{print "RAM total/used/free",$2,$3,$4}'
