#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-150; }
echo "== media services"; supervisorctl status | grep -iE "media|comfy|image|video|voice|tts|whisper|asr" | a
echo "== dirs"; ls -d /root/nox/media /root/nox/voice /root/nox/browsers /root/ComfyUI /opt/ComfyUI 2>/dev/null
du -sh /root/nox/media /root/nox/voice 2>/dev/null
echo "== media files (top)"; find /root/nox/media /root/nox/voice -maxdepth 3 \( -name "*.safetensors" -o -name "*.ckpt" -o -name "*.gguf" -o -name "*.onnx" -o -name "*.pth" \) -size +50M -exec ls -lh {} \; 2>/dev/null | awk '{print $5,$9}' | head -15
echo "== scripts"; ls /root/nox/scripts | grep -iE "media|image|video|comfy|voice|tts|asr" | head -15
echo "== ports"; for p in 8188 8189 7860 18779; do echo $p $(curl -s -m 3 -o /dev/null -w %{http_code} http://127.0.0.1:$p/); done
