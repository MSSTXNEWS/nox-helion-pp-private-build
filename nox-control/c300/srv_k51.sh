echo "C300: srv_k51"
cb=$(date +%s); curl -s -m 30 "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/draw/bench_sd.sh?cb=$cb" -o /workspace/nox/ops/draw/bench_sd.sh; chmod +x /workspace/nox/ops/draw/bench_sd.sh; wc -l /workspace/nox/ops/draw/bench_sd.sh
ls /workspace/nox/models/flux | head -12
curl -s -m 20 -o /dev/null -w "taef1 hf %{http_code}\n" -I https://huggingface.co/madebyollin/taef1/resolve/main/diffusion_pytorch_model.safetensors
tail -n 4 /workspace/nox/ops/dpo/run.log 2>&1 | cut -c1-200
