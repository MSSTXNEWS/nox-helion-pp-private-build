#!/bin/bash
D=/root/nox/dl; ls -la $D/logs | head -20; tail -c 500 $D/logs/hf_qwen3_4b.log; echo ---; tail -c 400 $D/logs/hf_reranker.log; hf --version; ls $D/hf/*/ 2>/dev/null | head; tail -5 $D/logs/deps.log
