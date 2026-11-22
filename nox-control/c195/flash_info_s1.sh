#!/bin/bash
echo "== flash.py"; head -c 1800 /root/nox/flash.py
echo; echo "== flash.log"; tail -c 700 /root/nox/logs/flash.log; echo "== out"; tail -c 400 /root/nox/logs/flash.out
echo "== procs"; ps -eo pid,etimes,pcpu,args | grep -E "llama-server" | grep -v grep | sed -E 's/ -(c|b|ub|fa|np|t|tb|amb) .*//' | cut -c1-170
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader; ls /root/nox/llama.cpp-f/build/bin/llama-server
