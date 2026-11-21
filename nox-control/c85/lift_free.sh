#!/bin/bash
# c85: по прямому решению владельца: (1) снять STOP_T131U/T134U/T135U (переименованием, обратимо), (2) удалить nox_lean_fallback (8.4 GB)
S=/root/nox/state; TS=$(date +%m%d_%H%M)
echo "== before"; df -h / | tail -1
for f in STOP_T131U STOP_T134U STOP_T135U; do
  if [ -e $S/$f ]; then echo "-- $f: $(head -c 160 $S/$f 2>/dev/null | tr '\n' ' ')"; mv $S/$f $S/$f.lifted_owner_$TS && echo "lifted $f"; else echo "no $f"; fi
done
M=/root/nox/models/nox_lean_fallback
if [ -d $M ]; then
  refs=$(grep -rl "nox_lean_fallback" /etc/supervisor/conf.d /root/nox/scripts 2>/dev/null | head -5)
  echo "refs: ${refs:-none}"
  if [ -z "$refs" ]; then du -sh $M; rm -rf $M && echo "deleted $M"; else echo "KEPT: referenced"; fi
else echo "no $M"; fi
echo "== after"; df -h / | tail -1
supervisorctl status 2>/dev/null | grep -E "train|dispatcher" | head -6
