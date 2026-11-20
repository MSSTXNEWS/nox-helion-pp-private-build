#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-160; }
S=/root/nox/scripts/run_train_t131u.sh
grep -nE "MIN_FREE|DATA|dataset|\.jsonl|python|CUDA_VISIBLE|sha|BASE|MODEL" $S | head -22 | a
echo "== py"; P=$(grep -oE "/root/nox/scripts/[a-z0-9_]+\.py" $S | head -3); echo $P; for p in $P; do grep -nE "argparse|add_argument\('--(data|model|out|max_steps|epochs)|DATA *=|jsonl" $p | head -8 | a; done
echo "== data files"; ls -la --time-style=+%F /root/nox/train_data /root/nox/datasets 2>/dev/null | tail -8 | a
echo "== embed"; grep -E "^\[program|^command" $(grep -l "embed" /etc/supervisor/conf.d/*.conf | head -2) | a; supervisorctl status | grep -i embed | a
