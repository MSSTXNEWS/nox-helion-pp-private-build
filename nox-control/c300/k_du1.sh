#!/bin/bash
echo K_DU1
df -h /workspace | tail -1
find /workspace -xdev -type f -mmin -600 -size +200M -printf '%s %TY-%Tm-%Td %TH:%TM %p\n' 2>/dev/null | sort -rn | head -20 | awk '{printf "%.1fG %s %s %s\n",$1/1e9,$2,$3,$4}'
echo ---TOP
du -xh --max-depth=2 /workspace 2>/dev/null | sort -rh | head -25
