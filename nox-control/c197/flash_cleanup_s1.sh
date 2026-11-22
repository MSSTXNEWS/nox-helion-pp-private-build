#!/bin/bash
D=/dev/shm/glm53f
pkill -f "hf download unsloth/GLM-5.3-Flash"; sleep 2
if pgrep -af "hf download|flash.py" | grep -v pgrep >/dev/null; then echo "ABORT: загрузка/flash.py ещё работает"; pgrep -af "hf download|flash.py" | cut -c1-100; exit 0; fi
python3 - <<'PY'
import os,sys
exp={1:9429984,2:49198039200,3:49988626304,4:48700701344,5:49026026752,6:2784497888}
bad=[n for n,s in exp.items() if not os.path.exists(f"/dev/shm/glm53f/GLM-5.3-Flash-UD-Q4_K_XL-0000{n}-of-00006.gguf") or os.path.getsize(f"/dev/shm/glm53f/GLM-5.3-Flash-UD-Q4_K_XL-0000{n}-of-00006.gguf")!=s]
print("основные шарды:", "ВСЕ 6 ЦЕЛЫЕ" if not bad else "НЕ ЦЕЛЫЕ %s"%bad)
sys.exit(1 if bad else 0)
PY
[ $? -ne 0 ] && { echo "ABORT: шарды не целые, ничего не удаляю"; exit 0; }
echo "до: $(df -h /dev/shm | tail -1)"; du -sh $D/.cache $D/UD-Q4_K_XL $D/Shard_Rewrite 2>/dev/null
rm -rf "$D/.cache" "$D/UD-Q4_K_XL" "$D/Shard_Rewrite"
echo "после: $(df -h /dev/shm | tail -1)"; ls -la $D | head -12
