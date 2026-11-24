#!/bin/bash
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300; S=/workspace/nox/web/site
for f in photo.html nox-photo.js; do curl -fsSL $R/$f -o $S/$f; done; echo deployed
D=/workspace/nox/models/first/silveroxides/Chroma1-HD-GGUF
if [ ! -s $D/ae.safetensors ]; then
 ( for u in https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors; do
     curl -fL --retry 3 -o $D/ae.safetensors.part "$u" && mv $D/ae.safetensors.part $D/ae.safetensors && echo "vae ok from $u" && break; done ) > /workspace/nox/agent/out/c300_vae.log 2>&1 &
fi
sleep 100; cat /workspace/nox/agent/out/c300_vae.log | tail -2; ls -la $D; curl -s -m5 127.0.0.1:8091/img/health | head -c 300
