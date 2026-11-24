S=/workspace/nox/web/site
echo "== reg"; head -c 3000 /workspace/nox/web/pkg/server/svc_registry.json
echo; echo "== start_all"; cat /workspace/nox/svc/start_all.sh | head -50
echo "== svc dirs"; ls /workspace/nox/svc
echo "== models dir"; ls /workspace/nox/models | head -30; du -sh /workspace/nox/models /workspace/nox/hf_home 2>/dev/null
echo "== tts"; ls /workspace/nox/c300_voice /workspace/nox/svc/tts* 2>/dev/null | head -30; ss -ltnp 2>/dev/null | grep -E ":(8093|8094|8500|9090|7700|8098|8096|4533)" | cut -c1-120
echo "== pages sizes"; for p in voice music photo studio knowledge news cinema tv; do wc -c $S/$p.html; done
echo "== voice.html"; head -c 3500 $S/voice.html
echo "== pip"; which python3 pip3; python3 -c "import torch;print(torch.__version__, torch.cuda.is_available())"; pip3 list 2>/dev/null | grep -iE "torch|transformers|diffusers|onnx|kokoro|espnet|piper|fastapi|uvicorn|flask|soundfile|phonem"
ls /workspace/nox/imgsvc | head; ls /workspace/nox/tools/engines | head -30
which espeak-ng ffmpeg
