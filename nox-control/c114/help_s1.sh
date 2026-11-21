#!/bin/bash
B=/root/nox/llama.cpp/build/bin/llama-server; export LD_LIBRARY_PATH=/usr/local/cuda-12.9/targets/x86_64-linux/lib:/root/nox/llama.cpp/build/bin
$B --help 2>&1 | grep -E -- "--moe-cache|--ubatch|--batch-size|--reasoning|--spec|ngram|--cache-reuse|--cache-type|--ctx-size|--thinking|--chat-template-kwargs|--mtp|--load-mode" | cut -c1-170 | head -30
cd /root/nox/llama.cpp && git log -1 --format="%h %ad" --date=short
