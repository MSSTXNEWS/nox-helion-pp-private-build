echo "C300: srv_k14"
cd /workspace/nox
ls -t distill_v2/rounds | head -5
R=$(ls -td distill_v2/rounds/* | head -1); echo R=$R; ls -t $R | head -12
tail -n 12 state/p3/ledger_srv.txt | cut -c1-300
tail -n 5 state/p3/repin.log | cut -c1-250
P=$(pgrep -f "python -I distill_v2.py" | head -1); echo P=$P; readlink /proc/$P/cwd; tr '\0' ' ' </proc/$P/environ | grep -o "MOE[^ ]*\|UNSLOTH[^ ]*\|LIGER[^ ]*\|NOX_[A-Z_]*=[^ ]*" | head -20
D=$(readlink /proc/$P/cwd); wc -l $D/distill_v2.py; grep -n "moe_backend\|unsloth_triton\|liger\|torch.compile\|get_peft\|r=\|lora_alpha\|max_seq\|per_device\|gradient_accum\|learning_rate\|load_in\|from_pretrained" $D/distill_v2.py | cut -c1-200 | head -30
./venv/bin/pip list 2>/dev/null | grep -i -E "^(trl|peft|unsloth|liger|torch|transformers|vllm|mlora|bitsandbytes|flash)" 
grep -n "MOE\|moe_backend" agent/autotrain/autotrain.sh | head
