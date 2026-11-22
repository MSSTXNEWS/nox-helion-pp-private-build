#!/bin/bash
# kit2: печать 00_START_HERE_RU.md кусками по 2800 байт (счётчик на S1)
F=$(ls -d /root/nox_kit_*/out | head -1)/00_START_HERE_RU.md; C=/root/.kit2_ctr
n=$(cat $C 2>/dev/null || echo 0); echo $((n+1)) > $C
echo "CHUNK $n"; tail -c +$((n*2800+1)) "$F" | head -c 2800
