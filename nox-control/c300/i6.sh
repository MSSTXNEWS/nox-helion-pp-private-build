R=/workspace/nox/invoke_root; mkdir -p $R /workspace/nox/models/invoke
cat > $R/invokeai.yaml <<Y
schema_version: 4.0.2
host: 127.0.0.1
port: 9090
allow_origins: []
Y
cat > /workspace/nox/svc/start_extra.sh <<'Y'
#!/bin/bash
(echo > /dev/tcp/127.0.0.1/9090) 2>/dev/null || { nohup setsid /workspace/nox/invoke/bin/invokeai-web --root /workspace/nox/invoke_root >/workspace/nox/svc/logs/invoke.log 2>&1 & }
Y
chmod +x /workspace/nox/svc/start_extra.sh
nohup setsid bash -c 'curl -fL -o /workspace/nox/models/invoke/DreamShaper_8_pruned.safetensors https://huggingface.co/Lykon/DreamShaper/resolve/main/DreamShaper_8_pruned.safetensors > /workspace/nox/models/invoke/dl.log 2>&1' >/dev/null 2>&1 &
nohup setsid bash /workspace/nox/svc/start_extra.sh >/dev/null 2>&1 &
sleep 90
tail -15 /workspace/nox/svc/logs/invoke.log | cut -c1-220
curl -s -m5 -o /dev/null -w "api %{http_code}\n" localhost:9090/api/v1/app/version; curl -s -m5 localhost:9090/ | head -c 600
ls -la /workspace/nox/models/invoke
