#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-230; }
for s in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag /root/nox/program/STOP /workspace/NOX_STOP; do [ -e $s ] && echo "STOP flag present: $s"; done
OUT=/root/nox/lora/qwen35_9b_t131u
echo "== out"; ls -la --time-style=+%m-%d_%H:%M $OUT | awk '{print $5,$6,$7}' | tail -14
echo "== log"; tail -n 14 /root/nox/logs/train_qwen9b_t131u.log | a
echo "== done/sha"; cat $OUT/DATA_SHA 2>/dev/null; ls $OUT/DONE* 2>/dev/null
echo "== early stop/guard"; grep -nE "early_stop|bad_evals|PATIENCE|patience|stop_during_staging" /root/nox/scripts/train_qwen35_9b_t131u.py | head -10 | a
echo "== corpus"; ls -la --time-style=+%m-%d_%H:%M /root/nox/state/qwen_corpus/*/ 2>/dev/null | awk '{print $5,$6,$7}' | tail -12; wc -l /root/nox/state/qwen_corpus/6907283384/train.jsonl
echo "== gpu"; nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader
