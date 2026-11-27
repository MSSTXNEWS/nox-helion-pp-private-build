echo "K1: l1_inner2"
cd /workspace/nox
f=$(find . -name nox_inner_loop.py -not -path "*/tmp/*" 2>/dev/null | head -3); echo "$f"
grep -rln "мыслей не отвечает" --include=*.py . 2>/dev/null | head -5
for x in $f; do grep -n "не отвечает\|NOX_FAST_URL\|NOX_SEED_URL\|8104\|8105\|timeout\|def .*llm" $x | cut -c1-200 | head -20; done
grep -c "мыслей не отвечает" state/*.log logs/*.log 2>/dev/null | grep -v ":0" | head -5
