#!/bin/bash
D=/root/nox/dl; head -c 400 $D/logs/hf_qwen3_4b.log; echo; which hf huggingface-cli; python3 -c "import huggingface_hub as h;print(h.__version__)"; curl -sI -m 8 https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf | head -3
