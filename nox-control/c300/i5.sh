cat > /workspace/nox/invoke_install2.sh <<'EOF'
V=/workspace/nox/invoke
printf '%s\n%s\n' /workspace/nox/venv/lib/python3.10/site-packages /venv/main/lib/python3.10/site-packages > $V/lib/python3.10/site-packages/zz_nox_main.pth
$V/bin/python - <<'P' > /tmp/ivk_req.txt
import importlib.metadata as m
from packaging.requirements import Requirement
for r in m.requires('invokeai') or []:
    q=Requirement(r)
    if q.marker and 'extra' in str(q.marker): continue
    if q.name.lower() in ('torch','torchvision','torchaudio'): continue
    print(r)
P
wc -l /tmp/ivk_req.txt
$V/bin/pip install --no-cache-dir -r /tmp/ivk_req.txt 2>&1 | grep -v "^Requirement already\|^  Using\|Downloading\|━" | tail -15
$V/bin/python -c "import torch,invokeai;print(torch.__version__,torch.cuda.is_available())" 2>&1 | tail -3
$V/bin/pip check 2>&1 | head -8
df -h /workspace | tail -1
echo INV2_DONE
EOF
nohup setsid bash /workspace/nox/invoke_install2.sh > /workspace/nox/invoke_install2.log 2>&1 &
sleep 150; tail -25 /workspace/nox/invoke_install2.log | cut -c1-220
