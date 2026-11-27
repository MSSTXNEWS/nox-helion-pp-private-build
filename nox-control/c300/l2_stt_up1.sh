echo "K1: l2_stt_up1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; VV=$N/voice_venv; M=$N/voice_models/whisper-large-v3-turbo
df -h /workspace | tail -1 | awk '{print $4}'
grep -n -E "\"/(synth|tts|speak|api)[a-z/]*\"|startswith\(\"/|path ==" $N/c300_voice/voice/tts_server.py | cut -c1-160 | head -8
[ -f $M/model.bin ] || $VV/bin/python - <<'PY'
from huggingface_hub import snapshot_download
p=snapshot_download("deepdml/faster-whisper-large-v3-turbo-ct2", local_dir="/workspace/nox/voice_models/whisper-large-v3-turbo")
print("dl",p)
PY
ls -la $M | head; du -sh $M
# CUDA libs from main venv (torch)
L=$(ls -d $N/venv/lib/python3*/site-packages/nvidia/*/lib 2>/dev/null | tr '\n' ':'); echo "libs: $(echo $L | tr ':' '\n' | wc -l)"
echo "pip nvidia in voice_venv:"; ls $VV/lib/python3*/site-packages | grep -i nvidia | head -3
