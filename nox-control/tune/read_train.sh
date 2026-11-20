#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-170; }
for P in nox-train-volta-t866u nox-train-qwen9b-t131u nox-selfheal nox-self-learning-loop; do
  C=$(grep -l "program:$P\]" /etc/supervisor/conf.d/*.conf 2>/dev/null | head -1)
  echo "=== $P ($C)"; grep -E "^(command|environment|stderr_logfile|stdout_logfile)=" "$C" 2>/dev/null | a | head -4
  L=$(grep -E "^stderr_logfile=" "$C" 2>/dev/null | cut -d= -f2 | head -1); [ -f "$L" ] && tail -6 "$L" | a
done
echo "== train state"; for f in /root/nox/state/TRAIN_T131U_STATUS.json /root/nox/state/TRAIN_T866U_STATUS.json; do [ -f $f ] && { echo $f; head -c 500 $f | a; echo; }; done
echo "== lora dirs"; ls -la /root/nox/lora 2>/dev/null | head -8 | a; ls /root/nox/models/lora | head -5
echo "== train scripts"; ls /root/nox/scripts | grep -iE "train|lora|distill|forge" | head -14
echo "== dense candidate"; ls /root/nox/models/nox_lean_fallback | head -4; du -sh /root/nox/models/nox_lean_fallback
