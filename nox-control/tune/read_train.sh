#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-170; }
echo "== conf"; grep -hE "^(command|environment|autostart)" /etc/supervisor/conf.d/nox-train-qwen9b-t131u.conf | a
echo "== status json"; head -c 700 /root/nox/state/TRAIN_T131U_STATUS.json | a; echo
echo "== train script"; S=$(grep -h '^command' /etc/supervisor/conf.d/nox-train-qwen9b-t131u.conf | grep -oE '/root/[^ ]+\.(py|sh)' | head -1); echo $S; grep -nE "CUDA_VISIBLE|device|cuda:|load_in|bnb|4bit|bf16|fp16|r=|lora_alpha|base_model|model_path|MODEL" $S 2>/dev/null | head -14 | a
echo "== lora/datasets"; ls -la /root/nox/lora 2>/dev/null | head -8 | a; du -sh /root/nox/datasets /root/nox/lora 2>/dev/null
echo "== lean fallback"; ls /root/nox/models/nox_lean_fallback | head -5; 
echo "== gpu procs"; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
