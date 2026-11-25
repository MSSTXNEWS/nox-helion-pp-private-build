#!/bin/bash
# s2_probe2.sh: чтение: исходник моста Диска (маршруты), без секретов
PID=$(ss -ltnp 2>/dev/null | grep ':18765' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo pid=$PID
[ -n "$PID" ] && { tr '\0' ' ' </proc/$PID/cmdline; echo; ls -l /proc/$PID/cwd; }
F=$(tr '\0' '\n' </proc/$PID/cmdline | grep '\.py$' | head -1); echo F=$F
[ -f "$F" ] || F=$(ls -l /proc/$PID/cwd | sed 's/.*-> //')/$F
grep -n 'path\|route\|startswith\|def do_\|== "/' "$F" 2>/dev/null | grep -vi 'token\|secret\|password' | head -60 | cut -c1-200
wc -l "$F"
