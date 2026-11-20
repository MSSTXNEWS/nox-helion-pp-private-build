#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-200; }
for s in run_train_volta_t866u.sh run_train_t131u.sh; do echo "=== $s"; head -c 1500 /root/nox/scripts/$s | a; echo; done
for P in nox-train-volta-t866u nox-train-qwen9b-t131u nox-distill-worm-t811u nox-knowledge-index-t168u; do C=$(grep -l "program:$P\]" /etc/supervisor/conf.d/*.conf|head -1); L=$(grep -E "^(stderr|stdout)_logfile=" $C | cut -d= -f2 | head -1); echo "=== $P log $L"; supervisorctl status $P | a; tail -4 "$L" 2>/dev/null | a; done
for f in /root/nox/state/TRAIN_T866U_STATUS.json /root/nox/state/TRAIN_T131U_STATUS.json /root/nox/state/MONITOR_T131U_LATEST.json; do echo "== $f"; head -c 600 $f 2>/dev/null | a; echo; done
echo "== big dirs"; du -sh /root/nox/models/* /root/nox/checkpoints /root/nox/lora /root/.cache/huggingface /opt/* 2>/dev/null | sort -h | tail -12
