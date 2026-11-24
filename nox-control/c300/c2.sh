python3 -m zipfile -l /tmp/ivk/invokeai-6.9.0-py3-none-any.whl 2>/dev/null | grep METADATA | head -1
unzip -p /tmp/ivk/invokeai-6.9.0-py3-none-any.whl 'invokeai-6.9.0.dist-info/METADATA' | grep -i "^Requires-Python\|^Requires-Dist: torch\|^Requires-Dist: diffusers\|^Requires-Dist: gguf\|^Requires-Dist: bitsandbytes\|^Requires-Dist: transformers"
unzip -p /tmp/ivk/invokeai-6.9.0-py3-none-any.whl 'invokeai/backend/model_manager/taxonomy.py' | grep -i "chroma\|gguf" | head -8
unzip -l /tmp/ivk/invokeai-6.9.0-py3-none-any.whl | grep -i chroma | head -5
nvidia-smi | grep -i "driver"
which uv; python3.11 --version 2>&1 | head -1
echo; for s in filebrowser navidrome jellyfin freshrss ntfy; do echo -n "$s "; curl -s -m 8 -o /dev/null -w "%{http_code} " localhost:8091/svc/$s/; done; echo
curl -s localhost:8091/svc/_status | cut -c1-600
tail -3 /workspace/nox/svc/logs/jellyfin.log | cut -c1-200
