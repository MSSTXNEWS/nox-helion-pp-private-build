#!/bin/bash
D=/dev/shm/glm53f
pkill -f "hf download unsloth/GLM-5.3-Flash"; sleep 3; pgrep -af "hf download" | head -2
echo "== shm"; df -h /dev/shm | tail -1
du -sh $D $D/.cache 2>/dev/null
python3 - <<'PY'
from huggingface_hub import HfApi
i=HfApi().model_info("unsloth/GLM-5.3-Flash-GGUF",files_metadata=True)
import os
ok=1
for s in i.siblings:
    if 'UD-Q4_K_XL' in s.rfilename and s.rfilename.endswith('.gguf'):
        p='/dev/shm/glm53f/'+s.rfilename
        a=os.path.getsize(p) if os.path.exists(p) else -1
        print(("OK " if a==s.size else "BAD"),a,s.size,s.rfilename); ok&=(a==s.size)
print("ALL_OK" if ok else "INCOMPLETE")
PY
find $D -maxdepth 2 -not -name "*.gguf" | head -8
