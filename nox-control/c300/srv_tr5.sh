#!/bin/bash
F=/workspace/nox/ops/liska_gates.py
wc -l $F; grep -n -E "^def |^    def |promot|rename|shutil|\"pass\"|'pass'|argv" $F | cut -c1-190 | head -70
grep -rn "liska_gates" /workspace/nox --include=*.sh --include=*.py -l 2>/dev/null | grep -v -E "bak|tmp|venv" | head
ls /workspace/nox/distill_v2/ckpt_keep/best* -d; ls -la /workspace/nox/distill_v2/ckpt_keep/ | head
