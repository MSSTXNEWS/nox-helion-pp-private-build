echo "C300: ac_chat2"
P=$(pgrep -f "port 8104" | head -1); tr '\0' ' ' </proc/$P/cmdline | cut -c280-700; echo
B=/workspace/nox/bin/llama-server; $B --help 2>&1 | grep -iE "spec-type|spec-ngram|mtp|--spec-draft-n-max|--spec-draft-p-min|cache-reuse|--cache-prompt|--slot-prompt" | cut -c1-220 | head -14
$B --help 2>&1 | grep -A6 -E "^--spec-type|, --spec-type" | cut -c1-200 | head -12
M=/workspace/nox/models/body/unsloth/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf
head -c 30000000 $M | grep -a -o -E "(nextn_predict_layers|[a-z0-9_]*mtp[a-z_.0-9]*|tokenizer.ggml.model|qwen35moe\.[a-z_.]*)" | sort -u | head -30
python3 - <<PY
import struct
f=open("$M","rb");f.read(8);nt,nkv=struct.unpack('<QQ',f.read(16));print('tensors',nt,'kv',nkv)
PY
head -c 20000000 /workspace/nox/models/gpu/Qwen/Qwen3-0.6B-GGUF/Qwen3-0.6B-Q8_0.gguf >/dev/null
ls -la /workspace/nox/models/gpu/Qwen/Qwen3-0.6B-GGUF/ | head -4
grep -c . /workspace/nox/state/LIVE_STATUS.txt; head -c 300 /workspace/nox/state/LIVE_STATUS.txt
