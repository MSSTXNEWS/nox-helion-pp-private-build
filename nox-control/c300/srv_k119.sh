echo "C300: srv_k119"
cd /workspace/nox; D=ops/dpo
for i in $(seq 25); do pgrep -f "ops/dpo/chain5.sh" >/dev/null || break; sleep 10; done
pgrep -f "ops/dpo/chain5.sh" >/dev/null && { echo "chain5 ещё идёт"; tail -n 3 $D/run5.log | cut -c1-150; exit 0; }
M=$(wc -l < ops/teacher_answers/mistral_small32.jsonl); G=$(wc -l < ops/teacher_answers/gpt_oss_20b.jsonl 2>/dev/null || echo 0); echo "ответы mistral=$M gpt_oss=$G"
if [ "$M" -ge 270 ] && [ "$G" -ge 270 ]; then
  cp -n serve/llama-swap.yaml serve/llama-swap.yaml.bak_k1_$(date +%Y%m%d)
  python3 - <<'PY'
import re
F="/workspace/nox/serve/llama-swap.yaml"; L=open(F).read().split("\n"); out=[]; skip=False
for l in L:
    if re.match(r'^  "(gpt-oss-20b|mistral-small-3\.2-24b)":', l): skip=True; continue
    if skip and l.startswith("    "): continue
    skip=False; out.append(l)
open(F,"w").write("\n".join(out)); print("yaml: блоки gpt-oss и mistral убраны")
PY
  for d in models/gpu/bartowski/mistralai_Mistral-Small-3.2-24B-Instruct-2506-GGUF models/gpu/unsloth/gpt-oss-20b-GGUF; do lsof +D $d >/dev/null 2>&1 && echo "занято $d" || { rm -rf $d && echo "УДАЛЕНО $d"; }; done
  df -h /workspace | tail -1
  sed -i 's|^dump(){ # dir name maxtok|&\n  [ -d "$1" ] \|\| return|' $D/chain5.sh; bash -n $D/chain5.sh && echo chain5_ok
  nohup setsid $D/chain5.sh </dev/null >/dev/null 2>&1 &
  sleep 20; tail -n 3 $D/run5.log | cut -c1-150
fi
