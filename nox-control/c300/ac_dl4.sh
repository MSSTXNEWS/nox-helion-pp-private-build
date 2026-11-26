echo "C300: ac_dl4"
pkill -f "curl -sL -C"; sleep 1
U=https://huggingface.co/unsloth/Qwen3-30B-A3B-Thinking-2507-GGUF/resolve/main/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf
F=/workspace/nox/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf
setsid -f bash -c "curl -L -C - --retry 20 --retry-delay 3 --retry-all-errors --speed-limit 1000000 --speed-time 30 -o $F $U" </dev/null >/tmp/dl_think2.log 2>&1
a=$(stat -c %s $F); sleep 45; b=$(stat -c %s $F); echo "MB/s $(( (b-a)/45/1048576 )) total $((b/1048576)) MB"; tail -c 300 /tmp/dl_think2.log | tr '\r' '\n' | tail -2
