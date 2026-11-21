#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-300; }
D=/root/nox/state/qwen_corpus/6907283384
echo "== train rows"; wc -l $D/train.jsonl $D/holdout.jsonl; head -n 2 $D/train.jsonl | a
python3 - <<'PY'
import json,collections
rows=[json.loads(l) for l in open('/root/nox/state/qwen_corpus/6907283384/train.jsonl') if l.strip()]
print('keys',collections.Counter(tuple(sorted(r)) for r in rows).most_common(2))
PY
echo "== manifest"; head -c 700 $D/corpus_manifest.json | a; echo
echo "== miner/self-learning outputs"; ls -la --time-style=+%m-%d_%H:%M /root/nox/state 2>/dev/null | grep -iE "dialog|mined|learn|corpus|kb" | awk '{print $5,$6,$7}' | head -12
supervisorctl status nox-dialog-miner nox-self-learning-loop nox-knowledge-index-t168u | awk '{print $1,$2}'
tail -n 3 /root/nox/logs/dialog_miner.log 2>/dev/null | a
find /root/nox -maxdepth 3 -name "*.jsonl" -size +50k -mmin -1500 2>/dev/null | head -8
