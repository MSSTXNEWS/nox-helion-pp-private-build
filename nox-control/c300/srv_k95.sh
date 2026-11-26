echo "C300: srv_k95"
cd /workspace/nox
ls -d models/gpu/*/*istral* models/gpu/*/*gpt-oss* models/gpu/*/*Mistral* 2>/dev/null; du -sh models/gpu/unsloth/* models/gpu/bartowski/* 2>/dev/null | sort -h | tail -8
/workspace/nox/venv/bin/python -I - <<'PY'
import json,collections
c=collections.Counter()
for i,l in enumerate(open('/workspace/nox/distill_v2/rows_train.jsonl',encoding='utf8')):
    try: o=json.loads(l)
    except: continue
    c[str(o.get('teacher'))[:50]]+=1
print(c.most_common(14))
PY
ls /workspace/nox/ops | grep -i -E "ready_bulk|teacher_cache|logit" | head -5
ps aux | grep -E "llama-server" | grep -o "models/[a-z]*/[^ ]*gguf" | sort -u | head -14
