echo "C300: ac_dl2"
A=$(df -BG --output=avail /workspace | tail -1 | tr -dc 0-9); echo avail ${A}G
U=https://huggingface.co/unsloth/Qwen3-30B-A3B-Thinking-2507-GGUF/resolve/main/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf
SZ=$(curl -sIL -m 20 $U | grep -i "^content-length" | tail -1 | tr -dc 0-9); echo size $SZ
[ -z "$SZ" ] && exit
NEED=$(( SZ/1073741824 + 15 )); echo need ${NEED}G
[ $A -lt $NEED ] && { echo "NOT ENOUGH"; exit; }
D=/workspace/nox/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF; mkdir -p $D
setsid -f bash -c "curl -sL -C - --retry 8 --retry-delay 5 -o $D/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf $U" </dev/null >/tmp/dl_think.log 2>&1
sleep 120; ls -la $D | tail -1; df -h /workspace | tail -1
