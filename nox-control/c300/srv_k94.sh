echo "C300: srv_k94"
curl -s -m 25 "https://huggingface.co/api/models?search=Qwen3.6-35B-A3B&limit=30" | /workspace/nox/venv/bin/python -c "
import sys,json
for m in json.load(sys.stdin): print(m['id'], m.get('downloads'))"
for r in unsloth/Qwen3.6-35B-A3B-unsloth-bnb-4bit unsloth/Qwen3.6-35B-A3B-bnb-4bit; do curl -s -m 20 "https://huggingface.co/api/models/$r?blobs=true" | /workspace/nox/venv/bin/python -c "
import sys,json
try:
    d=json.load(sys.stdin); s=sum(x.get('size',0) for x in d['siblings']); print('$r', round(s/1e9,1),'ГБ', d.get('license') or d.get('cardData',{}).get('license'))
except Exception as e: print('$r нет', str(sys.stdin)[:0])"; done
du -sh /workspace/nox/models/student/Qwen/Qwen3.6-35B-A3B; ls /workspace/nox/models/student/Qwen/Qwen3.6-35B-A3B | head -5
df -h /workspace | tail -1
