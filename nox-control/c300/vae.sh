#!/bin/bash
f=/workspace/nox/imgsvc/image_service.py; grep -n "vae\|VAE\|ae.safetensors\|chroma" $f | head -20 | cut -c1-200
ls -la /workspace/nox/models/first/silveroxides/Chroma1-HD-GGUF/ /workspace/nox/models/first/ 2>/dev/null | head -20
