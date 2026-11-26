echo "C300: k2_r12"
N=/workspace/nox
S(){ sed -E 's/--master-key [^ ]+/--master-key ***/g;s/(key|token|secret)([=: ]+)[A-Za-z0-9_\-]{12,}/\1\2***/Ig'; }
echo "--- start_extra"; cat $N/svc/start_extra.sh | S | cut -c1-260
echo "--- who runs start_extra"; grep -rIl "start_extra" /etc/supervisor/conf.d $N/ops $N/agent/*.sh /.launch 2>/dev/null | head -3; crontab -l | grep -c start_extra
echo "--- 8143 state"; ps -o pid,stat,rss,args -p 3638858 | cut -c1-120
grep -nE "8143|t_coder" $N/stewards/*.py $N/state/orch/*.json $N/stewards/*.json $N/stewards/*.yaml 2>/dev/null | cut -c1-220 | head -12
echo "--- 8105 in orch"; grep -nE "8105|llama8105|subbase|Qwen3-30B" $N/stewards/*.py $N/stewards/*.json 2>/dev/null | cut -c1-240 | head -14
echo "--- thinking dl refs"; grep -rIl "Thinking-2507" $N/ops $N/agent $N/stewards $N/state/*.sh /workspace/*.sh 2>/dev/null | grep -v -E "\.bak|\.log" | head -5
ps -eo pid,etimes,stat,args | grep -E "curl|wget|huggingface|hf " | grep -v grep | grep -iE "gguf|huggingface" | cut -c1-200
echo "--- HF reach"; curl -sI -m 15 -L https://huggingface.co/unsloth/Qwen3-30B-A3B-Thinking-2507-GGUF/resolve/main/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf | grep -iE "^HTTP|content-length" | head -5
df -BG /workspace | tail -1
echo "--- llama-swap models"; grep -nE "^  [a-zA-Z0-9_.-]+:|8105|8104" $N/serve/llama-swap.yaml | head -20 | cut -c1-160
