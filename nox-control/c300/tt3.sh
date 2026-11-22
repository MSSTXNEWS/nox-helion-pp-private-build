#!/bin/bash
RU=/root/nox/dl/hf/piper_ru/ru/ru_RU/ruslan/medium/ru_RU-ruslan-medium.onnx
cp /root/nox/boot_s1.sh /root/nox/boot_s1.sh.bak_tts
sed -i "s|^export NOX_PIPER_MODEL_RU=\$P |export NOX_PIPER_MODEL_RU=$RU |" /root/nox/boot_s1.sh; grep -c "ruslan" /root/nox/boot_s1.sh; bash -n /root/nox/boot_s1.sh && echo boot ok
python3 /root/nox/env_restart.py 8094 NOX_PIPER_MODEL_RU=$RU | tail -1; sleep 12
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/tt.py -o /tmp/tt.py && /root/.nox-voice-venv/bin/python /tmp/tt.py 2>&1 | cut -c1-250
