F=/workspace/nox/invoke/lib/python3.10/site-packages/diffusers/quantizers/torchao/torchao_quantizer.py
head -3 $F; grep -n "logger\|^if \|^    if is_torchao\|^from\|^import" $F | head -30; sed -n 80,95p $F
