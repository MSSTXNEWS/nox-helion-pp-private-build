#!/bin/bash
# c300: голос на K1 (STT :8093, TTS :8094) из nox-control/voice. Лог: /workspace/nox/agent/out/c300_voice.log
L=/workspace/nox/agent/out/c300_voice.log; exec >>$L 2>&1; echo "== $(date -u +%T) start"
B=/workspace/nox/c300_voice; mkdir -p $B && cd $B
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/voice
mkdir -p voice; for f in __init__.py common.py textproc.py tts_server.py stt_server.py start_voice.sh install_deps.sh; do curl -fsSL $R/$f -o voice/$f || echo "dl fail $f"; done
python3 - <<'P'
import re
p="/workspace/nox/c300_voice/voice/textproc.py"; s=open(p).read()
m=re.search(r"def clean_for_tts\(([^)]*)\):\n((?:\s+\"\"\".*?\"\"\"\n)?)", s, re.S); a=m.group(1).split(",")[0].split("=")[0].strip()
if "Нокс Хелион" not in s:
    s=s[:m.end()]+'    %s = re.sub(r"\\bNOX\\b", "Нокс", re.sub(r"\\bNOX HELION\\b", "Нокс Хелион", %s or ""))\n'%(a,a)+s[m.end():]
    if not re.search(r"^import re\b|^import .*\bre\b", s, re.M): s="import re\n"+s
open(p,"w").write(s); print("textproc patched")
P
export NOX_VOICE_VENV=/workspace/nox/voice_venv NOX_VOICE_MODELS=/workspace/nox/voice_models NOX_VOICE_SKIP_TTS=1 NOX_VOICE_PIPER_VOICES="ru_RU-ruslan-medium es_ES-davefx-medium" NOX_VOICE_PREFETCH=1 NOX_STT_MODEL=small HF_HOME=/workspace/nox/hf_home
nice -n 10 bash voice/install_deps.sh
export NOX_PIPER_MODEL_RU=/workspace/nox/voice_models/ru_RU-ruslan-medium.onnx NOX_PIPER_MODEL_ES=/workspace/nox/voice_models/es_ES-davefx-medium.onnx NOX_TTS_BACKENDS=piper NOX_STT_DEVICE=cpu NOX_STT_THREADS=4 NOX_VOICE_LOGDIR=/workspace/nox/agent/out NOX_VOICE_RUNDIR=/workspace/nox/c300_voice/run
cat > /workspace/nox/c300_voice/start.sh <<S
#!/bin/bash
export NOX_VOICE_VENV=$NOX_VOICE_VENV NOX_VOICE_MODELS=$NOX_VOICE_MODELS NOX_PIPER_MODEL_RU=$NOX_PIPER_MODEL_RU NOX_PIPER_MODEL_ES=$NOX_PIPER_MODEL_ES NOX_TTS_BACKENDS=piper NOX_STT_DEVICE=cpu NOX_STT_THREADS=4 NOX_STT_MODEL=small HF_HOME=/workspace/nox/hf_home NOX_VOICE_LOGDIR=/workspace/nox/agent/out NOX_VOICE_RUNDIR=/workspace/nox/c300_voice/run
cd /workspace/nox/c300_voice && nice -n 5 bash voice/start_voice.sh all
S
chmod +x /workspace/nox/c300_voice/start.sh; bash /workspace/nox/c300_voice/start.sh
grep -q c300_voice/start.sh /root/onstart.sh 2>/dev/null || echo "(sleep 60; bash /workspace/nox/c300_voice/start.sh >> /workspace/nox/agent/out/c300_voice.log 2>&1) &" >> /root/onstart.sh
sleep 20; for p in 8093 8094; do echo "$p $(curl -s -m5 127.0.0.1:$p/health | head -c 200)"; done; echo "== DONE"
