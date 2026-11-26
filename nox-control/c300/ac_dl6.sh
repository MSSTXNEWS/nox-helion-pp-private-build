echo "C300: ac_dl6"
F=/workspace/nox/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf
a=$(stat -c %s $F); sleep 90; b=$(stat -c %s $F); echo "MB/s $(( (b-a)/90/1048576 )) total $((b/1048576)) MB"; tr '\r' '\n' </tmp/dl_think2.log | tail -2 | cut -c1-150
curl -s -m 20 -o /dev/null -w "probe %{http_code} %{speed_download} B/s\n" -r 0-20000000 https://huggingface.co/unsloth/Qwen3-30B-A3B-Thinking-2507-GGUF/resolve/main/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf -L
