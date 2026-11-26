#!/bin/bash
echo "C300: canon_probe3"
N=/workspace/nox
du -xsh $N/models/* 2>/dev/null | sort -rh | head -14
echo "== models depth2 top"
du -xh --max-depth=2 $N/models 2>/dev/null | sort -rh | sed -n '2,26p'
echo "== ops top"; du -xsh $N/ops/* 2>/dev/null | sort -rh | head -8
echo "== distill_v2 top"; du -xsh $N/distill_v2/* 2>/dev/null | sort -rh | head -6
echo "== big files >4G"; find $N -xdev -type f -size +4G -printf '%s %TY-%Tm-%Td %p\n' 2>/dev/null | sort -rn | awk '{printf "%.1fG %s %s\n",$1/1073741824,$2,$3}' | sed 's#/workspace/nox/##' | head -30
echo "== open by procs (gguf/safetensors)"; for p in $(pgrep -f 'llama|python|sd-server' | head -30); do ls -l /proc/$p/fd 2>/dev/null | grep -oE '/workspace/nox/[^ ]+\.(gguf|safetensors)' ; done | sort -u | head -15
