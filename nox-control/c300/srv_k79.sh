echo "C300: srv_k79"
D=/workspace/nox/ops/v5_live_adapter_20261125
F1=$D/r031-step200-148ac78dec059713.gguf; F2=$D/r031-step250-e4d8e922ebb36f56.gguf; F3=/workspace/nox/ops/v5_knowledge_gpu_20261125/main-rows.jsonl.bak_add_accepted_long_20261125_step125
echo "DF до:"; df -h /workspace | tail -1
for f in $F1 $F2 $F3; do
  b=$(basename $f)
  if lsof "$f" >/dev/null 2>&1; then echo "SKIP открыт: $b"; continue; fi
  if grep -q "$b\|r031-step200\|r031-step250" /workspace/nox/serve/llama-swap.yaml 2>/dev/null; then echo "SKIP в llama-swap: $b"; continue; fi
  s=$(stat -c %s $f); rm -f "$f" && echo "УДАЛЁН $f $s байт"
done
echo "DF после:"; df -h /workspace | tail -1
echo "остались gguf:"; ls $D/*.gguf | xargs -n1 basename
