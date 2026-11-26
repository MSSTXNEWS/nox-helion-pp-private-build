echo "C300: srv_k89"
echo "DF до:"; df -h /workspace | tail -1
K=/workspace/nox/distill_v2/ckpt_keep; D=/workspace/nox/ops/v5_live_adapter_20261125
TOT=0
for f in $D/r028-step125-d9cb3bdf7ea35b57.gguf $D/r028-step175-b7443dd38564b106.gguf $D/r031-step150-125b1a167d595d96.gguf $K/cand_dpo_11260733 $K/cand_dpo_11260733_trainer $K/cand_dpo_11260743 $K/cand_dpo_11260743_trainer $K/cand_dpo_11260749 $K/cand_dpo_11260749_trainer; do
  [ -e "$f" ] || { echo "нет: $f"; continue; }
  b=$(basename $f)
  if lsof +D "$f" >/dev/null 2>&1 || lsof "$f" >/dev/null 2>&1; then echo "SKIP открыт: $b"; continue; fi
  if grep -q "$b" /workspace/nox/serve/llama-swap.yaml /workspace/nox/state/orch_registry.json /workspace/nox/state/*.json 2>/dev/null; then echo "SKIP в конфиге: $b"; continue; fi
  s=$(du -sb "$f" | cut -f1); rm -rf "$f" && { echo "УДАЛЁН $f $s"; TOT=$((TOT+s)); }
done
echo "ИТОГО удалено байт: $TOT"
echo "DF после:"; df -h /workspace | tail -1
echo "остались:"; ls -d $K/cand_dpo_* $D/*.gguf | xargs -n1 basename
