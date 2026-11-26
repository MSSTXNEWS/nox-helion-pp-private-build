echo "C300: ac_mb8"
F=/workspace/nox/distill_v2/code/distill_v2.py
sed -n 1648,1672p $F | cut -c1-200
grep -n "def cmd_train\|def train(\|args = ap.parse_args\|a = ap.parse_args\|parse_args" $F | head; sed -n 2836,2850p $F | cut -c1-160
grep -n "готово\|log(\"итог\|return res" $F | tail -6 | cut -c1-140
