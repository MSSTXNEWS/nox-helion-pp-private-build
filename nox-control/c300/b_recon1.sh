echo "== disk"; df -h /workspace | tail -1; nvidia-smi --query-gpu=memory.used,memory.total --format=csv
curl -s http://127.0.0.1:8091/glm/v1/nox/stats | head -c 300; echo
cd /workspace/nox/web/site; ls; ls qa 2>/dev/null | head; wc -c voice.html music.html photo.html studio.html knowledge.html news.html movies.html cinema.html 2>&1
ls /workspace/nox/svc; cat /workspace/nox/svc/start_all.sh | head -60
cat /workspace/nox/web/pkg/server/svc_registry.json | head -c 2500
ls /workspace/nox/tools /workspace/nox/models 2>/dev/null | head -50
python3 --version; pip --version; ls /workspace/nox/venvs 2>/dev/null
ps aux | grep -E "tts|piper|imgsvc" | grep -v grep | head
