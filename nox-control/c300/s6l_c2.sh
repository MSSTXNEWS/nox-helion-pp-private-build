echo "K1: s6l_c2"
cat /workspace/nox/ops/dpo/mix_data.py
echo ---; grep -n "dpo_inj\|mix_data\|dpo_.*jsonl\|hold\|eval" /workspace/nox/ops/dpo/char_cycle.sh | cut -c1-200 | head -20
echo "## gates persona"; grep -n -i "persona\|soul_recognition\|honesty" /workspace/nox/ops/dpo/rel_gates.py | cut -c1-160 | head -12
df -BG /workspace | tail -1
echo END
