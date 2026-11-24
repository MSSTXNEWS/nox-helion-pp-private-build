cat > /workspace/nox/invoke_install.sh <<'EOF'
set -x
V=/workspace/nox/invoke
python3 -m venv $V
SP=$($V/bin/python -c "import site;print(site.getsitepackages()[0])")
echo /workspace/nox/venv/lib/python3.10/site-packages > $SP/zz_nox_main.pth
$V/bin/pip install --no-cache-dir -q --upgrade pip
$V/bin/pip install --no-cache-dir --no-deps invokeai==6.9.0 2>&1 | tail -2
$V/bin/python - <<'P' > /tmp/ivk_req.txt
import importlib.metadata as m
from packaging.requirements import Requirement
for r in m.requires('invokeai') or []:
    q=Requirement(r)
    if q.marker and 'extra' in str(q.marker): continue
    if q.name.lower() in ('torch','torchvision','torchaudio'): continue
    print(r)
P
cat /tmp/ivk_req.txt | wc -l
$V/bin/pip install --no-cache-dir -r /tmp/ivk_req.txt 2>&1 | tail -5
$V/bin/python -c "import torch,invokeai;print(torch.__version__,torch.cuda.is_available())" 2>&1 | tail -2
$V/bin/pip check 2>&1 | head -10
df -h /workspace | tail -1
echo INV_DONE
EOF
nohup setsid bash /workspace/nox/invoke_install.sh > /workspace/nox/invoke_install.log 2>&1 &
sleep 5; echo started
