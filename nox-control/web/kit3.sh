#!/bin/bash
# kit3: чтение (без изменений) — листинг и 01_BEGIN_LIVING_NOX.md кусками
O=$(ls -d /root/nox_kit_*/out | head -1); C=/root/.kit3_ctr
n=$(cat $C 2>/dev/null || echo 0); echo $((n+1)) > $C; echo "CHUNK $n"
if [ $n = 0 ]; then cd $O; ls -l 12_Living_NOX 08_Live_Chat_Memory_Architecture 10_Soul_Implementation_Deltas | cut -c20-; cat LIMITS_AND_REFERENCES.md | head -c 1500
else tail -c +$(((n-1)*2800+1)) $O/12_Living_NOX/01_BEGIN_LIVING_NOX.md | head -c 2800; fi
