#!/bin/bash
E=/workspace/nox/state/p3/eval
sed -i 's/python -I -m lm_eval/python -m lm_eval/' $E/run_eval.sh
setsid -f $E/run_eval.sh base > /dev/null 2>&1 < /dev/null
sleep 120; tail -12 $E/run_base.log | cut -c1-220
