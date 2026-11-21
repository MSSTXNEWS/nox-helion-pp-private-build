#!/bin/bash
# замер ток/с: 3 запроса (короткий, русский, длиннее)
for p in "Привет! Кто ты?" "Объясни по-русски, чем MoE-модель отличается от плотной, в 5 предложениях." "Напиши функцию на Python, которая проверяет простое число, и объясни её."; do
 curl -s http://127.0.0.1:8081/completion -d "$(python3 -c "import json,sys;print(json.dumps({'prompt':sys.argv[1],'n_predict':120,'cache_prompt':False}))" "$p")" | python3 -c "
import sys,json; d=json.load(sys.stdin); t=d['timings']; print('prompt %.1f t/s (%d tok) | gen %.2f t/s (%d tok)'%(t['prompt_per_second'],t['prompt_n'],t['predicted_per_second'],t['predicted_n'])); print(d['content'][:160].replace('\n',' '))"
done
grep -iE "offloaded|CUDA0 model|CPU_Mapped|KV" /root/nox/logs/glm_server.log | head -6 | cut -c1-160
nvidia-smi --query-gpu=memory.used --format=csv,noheader
