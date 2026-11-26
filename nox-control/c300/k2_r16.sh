echo "C300: k2_r16"
N=/workspace/nox
grep -rIl "мессиром или" $N/web $N/brain $N/state/*.json $N/integration $N/ops 2>/dev/null | grep -v -E "\.bak|\.log|vendor" | head -5
grep -rIh "мессиром или" $N/web/pkg $N/brain 2>/dev/null | grep -v -E "^\s*#" | head -3 | cut -c1-300
