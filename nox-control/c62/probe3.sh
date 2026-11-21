#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-260; }
echo "== trainer fail"; grep -rn "no micro-batch fits" /root/nox/scripts/train_qwen35_9b_t131u.py | head -3 | a
grep -nE "MICRO|micro_batch|BATCH|MAXLEN|max_len|SEQ|load_in_4bit|gradient_checkpointing" /root/nox/scripts/train_qwen35_9b_t131u.py | head -14 | a
tail -n 6 /root/nox/logs/train_qwen9b_t131u.log | a
echo "== queue.jsonl"; wc -l /root/nox/state/dispatcher/queue.jsonl; tail -n 3 /root/nox/state/dispatcher/queue.jsonl | a
echo "== state"; head -c 500 /root/nox/state/dispatcher/state.json | a; echo
echo "== catalog"; python3 -c "
import json;d=json.load(open('/root/nox/tasks/1000_tasks_20261117.dispatcher.json'));print(type(d).__name__,list(d)[:8] if isinstance(d,dict) else len(d))
x=d if isinstance(d,list) else next((v for v in d.values() if isinstance(v,list)),[]);print(len(x),json.dumps(x[0],ensure_ascii=False)[:400] if x else '')" | a
echo "== dispatcher pick"; grep -nE "def pick_ready|def .*enqueue|queue.jsonl|\"status\"" /root/nox/scripts/nox_dispatcher_t855u.py | head -12 | a
