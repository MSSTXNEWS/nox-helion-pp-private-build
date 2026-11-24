cd /workspace/nox/web
df -h /workspace | tail -1
which docker; docker ps 2>&1 | head -3
ls site | grep -c html; ls site | head -80 | tr '\n' ' '; echo
python3 -c "import json;d=json.load(open('site/nav.json'));print(json.dumps(d,ensure_ascii=False)[:2500])"
grep -n "svc\|def do_\|/drive/" pkg/server/web_server.py | head -30
wc -l pkg/server/web_server.py
cat /root/onstart.sh | tail -15 | cut -c1-200
ls /workspace/nox/models/first/silveroxides/Chroma1-HD-GGUF | head; python3 --version; ls /workspace/nox/venv/bin/python
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
