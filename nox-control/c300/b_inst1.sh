L=/workspace/nox/svc/logs/b_voice2_install.log; mkdir -p /workspace/nox/svc/logs
cat > /tmp/b_inst1.sh <<'EOS'
set -x
df -h /workspace | tail -1
V=/workspace/nox/voice2_venv
[ -d $V ] || python3 -m venv $V
$V/bin/pip install -q --upgrade pip
$V/bin/pip install -q torch --index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -3
$V/bin/pip install -q num2words pymorphy3 pymorphy3-dicts-ru onnxruntime soundfile numpy ruaccent omegaconf 2>&1 | tail -5
$V/bin/pip list 2>/dev/null | grep -iE "^(torch|num2words|pymorphy3|ruaccent|onnxruntime|numpy|transformers|huggingface)"
mkdir -p /workspace/nox/voice_models/silero
cd /workspace/nox/voice_models/silero
[ -s v5_ru.pt ] || curl -fsSL -o v5_ru.pt https://models.silero.ai/models/tts/ru/v5_ru.pt
[ -s v2_4lang_q.pt ] || curl -fsSL -o v2_4lang_q.pt https://models.silero.ai/te_models/v2_4lang_q.pt
ls -la
df -h /workspace | tail -1
echo INST_DONE
EOS
nohup setsid bash /tmp/b_inst1.sh > $L 2>&1 &
sleep 2; echo started
