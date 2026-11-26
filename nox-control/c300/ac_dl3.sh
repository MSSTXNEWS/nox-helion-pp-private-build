echo "C300: ac_dl3"
F=/workspace/nox/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf
a=$(stat -c %s $F); sleep 60; b=$(stat -c %s $F); echo "MB/s $(( (b-a)/60/1048576 )) total $((b/1048576)) MB"; pgrep -af "curl -sL -C" | wc -l; cat /tmp/dl_think.log | tail -2
