#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-300; }
D=/root/nox/state/qwen_corpus/6907283384
wc -l $D/*.jsonl; head -1 $D/train.jsonl | python3 -c "import json,sys;d=json.loads(sys.stdin.read());print({k:(str(v)[:150]) for k,v in d.items()})" | a
wc -l /root/nox/state/turns.jsonl /root/nox/state/feedback.jsonl 2>&1 | a; tail -1 /root/nox/state/turns.jsonl | python3 -c "import json,sys;d=json.loads(sys.stdin.read());print({k:(str(v)[:60]) for k,v in d.items()})" | a
S=/root/nox/scripts/train_qwen35_9b_t131u.py
grep -nE "BASE|load_in_4bit|MAX_LEN|max_len|BATCH|MAX_STEPS|max_steps|LR *=|\[.(messages|text|prompt|completion).\]" $S | head -14 | a
ls /root/nox/lora/qwen35_9b_t131u | tail -4 | tr '\n' ' '
