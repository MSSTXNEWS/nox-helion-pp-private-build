#!/bin/bash
N=/workspace/nox
echo "== after 8106 stop"; cat $N/state/p3/after_8106.txt
echo "== qa_audit lock/chat test"; grep -n -E "flock|lock|chat|max_tokens|timeout|send|fill|press" $N/qa_audit.py | cut -c1-170 | head -40
echo "== qa procs"; ps -eo pid,etimes,ni,args | grep -E "qa_audit|qa_ctl|one.py" | grep -v grep | cut -c1-170
echo "== qa_ctl head"; sed -n 1,30p $N/qa_ctl.py | cut -c1-170
