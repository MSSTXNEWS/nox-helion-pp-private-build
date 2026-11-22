#!/bin/bash
tr '\0' ' ' </proc/$(pgrep -f 'llama.cpp-f.*8081'|head -1)/cmdline | cut -c60-400; echo; taskset -cp $(pgrep -f 'llama.cpp-f.*8081'|head -1)
head -c 400 /tmp/gen.py; echo; ps -o etimes,args -p $(pgrep -f /tmp/gen.py) 2>/dev/null | tail -1 | cut -c1-80
grep -c "" /root/nox/start_glm.sh; grep -o "taskset -c [0-9-]*\|-t [0-9]* -tb [0-9]*\|--parallel [0-9]*\|-c [0-9]*" /root/nox/start_glm.sh | tr '\n' ' '
