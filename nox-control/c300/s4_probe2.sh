# S4 probe2: read-only. soul_recognition scoring + inj/ini case ids; HF reachability; python
N=/workspace/nox; F=$N/brain/GROW/upgrade/soul_recognition.py
echo "S4P2 $(date +%F_%H:%M)"
grep -n -e "^def " -e "^CASES\|^SOUL\|^[A-Z_]* *= *\[" $F | cut -c1-200 | head -50
echo "## ids"; grep -o '^    ("[a-z_0-9]*", "[a-z_]*", \(True\|False\)' $F | tr -d ' (' | tr '\n' ' ' | cut -c1-3000
echo; echo "## scoring"
grep -n -i -e "crit" -e "re.search" -e "re.I" $F | cut -c1-220 | head -40
echo "## who imports"; grep -rIl --include=*.py "soul_recognition" $N/distill_v2/code $N/ops $N/brain/SLP 2>/dev/null | head
echo "## HF"; curl -s -m 10 -o /dev/null -w "hf_api=%{http_code}\n" https://huggingface.co/api/datasets/deepset/prompt-injections
for p in venv/bin/python python3; do :; done
ls $N/ops/dpo | head -40; ls $N/ops/dpo/*.jsonl 2>/dev/null | head -20
echo "disk: $(df -BG --output=avail $N | tail -1)"
