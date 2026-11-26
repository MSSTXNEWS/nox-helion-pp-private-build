echo "C300: srv_k120"
cd /workspace/nox/svc/pipeline; sed -n 1,10p pipeline_svc.py | cut -c1-200; sed -n 95,219p pipeline_svc.py | cut -c1-210
ls; grep -c "" /workspace/nox/models/gpu/protectai/*/config.json 2>/dev/null | head -3; ls /workspace/nox/models/gpu/protectai
