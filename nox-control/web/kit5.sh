#!/bin/bash
C=/root/.kit5_ctr; n=$(cat $C 2>/dev/null || echo 0); echo $((n+1)) > $C; echo "CHUNK $n"
S=/root/nox/soul_kit
if [ $n = 0 ]; then
 ls /root/nox | head -40 | tr '\n' ' '; echo
 ls /root/nox/*.py 2>/dev/null | tr '\n' ' '; echo
 grep -rIl -i -E "persona|system_prompt|NOX_SYSTEM" /root/nox --include=*.py --include=*.json --include=*.md --include=*.txt --include=*.yaml 2>/dev/null | grep -v soul_kit | head -15
 ss -ltnp 2>/dev/null | grep -E ":80[0-9][0-9]|:8091|:8095" | awk '{print $4,$6}' | cut -c1-60
 ls /root/nox/s03* /root/nox/*/s03* 2>/dev/null | head; find /root -name "s03.db" 2>/dev/null | head -3
else tr -s ' \n' < $S/12_Living_NOX/01_BEGIN_LIVING_NOX.md | tail -c +$(((n-1)*2900+1)) | head -c 2900; fi
