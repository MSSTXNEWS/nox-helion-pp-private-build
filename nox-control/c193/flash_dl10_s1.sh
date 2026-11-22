#!/bin/bash
D=/dev/shm/glm53f; LOG=/root/nox/logs/flash_dl10.log
pip install -q -U "huggingface_hub[hf_transfer]" --break-system-packages 2>&1 | tail -1
sz(){ du -sb $D | cut -f1; }
echo "до: $(( $(sz)/1073741824 )) ГБ; процессы:"; pgrep -af "hf download|aria2c" | cut -c1-90
EXP=$(python3 - <<'PY'
from huggingface_hub import HfApi
i=HfApi().model_info("unsloth/GLM-5.3-Flash-GGUF",files_metadata=True)
t=sum(s.size or 0 for s in i.siblings if 'UD-Q4_K_XL' in s.rfilename); print(t)
PY
)
echo "ожидаемый размер: $((EXP/1073741824)) ГБ"
pkill -f "hf download unsloth/GLM-5.3-Flash" ; sleep 2
export HF_HUB_ENABLE_HF_TRANSFER=1
nohup setsid bash -c "hf download unsloth/GLM-5.3-Flash-GGUF --include '*UD-Q4_K_XL*' --local-dir $D --max-workers 10" > $LOG 2>&1 < /dev/null &
S0=$(sz); sleep 120; S1=$(sz)
echo "после 2 мин: скорость $(( (S1-S0)/120/1048576 )) МБ/с; скачано $((S1/1073741824)) ГБ; осталось $(( (EXP-S1)/1073741824 )) ГБ"
pgrep -af "hf download" | head -2 | cut -c1-90; tail -c 250 $LOG
ls -l $D/*.gguf | awk '{printf "%.1f ГБ %s\n",$5/1073741824,$9}'
