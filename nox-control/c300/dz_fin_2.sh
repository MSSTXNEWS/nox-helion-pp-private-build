S=/workspace/nox/web/site
if [ -f $S/nox-ghost.js ] && ! grep -q nox-ghost $S/creative.html; then sed -i 's#<script src="./nox-dz-creative.js#<script src="./nox-ghost.js" defer></script>\n<script src="./nox-dz-creative.js#' $S/creative.html; echo "ghost tag added"; else echo "ghost: file $( [ -f $S/nox-ghost.js ] && echo exists || echo absent )"; fi
grep -c "nox-s6-sl\|nox-s2-creative" $S/creative.html
echo "== fixed"; ls -la $S/qa/rework/creative.fixed $S/qa/rework/about.fixed; file $S/qa/rework/about.fixed | head -2; head -c 400 $S/qa/rework/about.fixed; echo; tail -c 300 $S/qa/rework/creative.fixed
echo "== k2_qa"; /workspace/nox/venv/bin/python /tmp/k2_qa.py creative 2>&1 | tail -4
grep -n "export\|NOXGhost\|window\." $S/nox-ghost.js 2>/dev/null | head -8 | cut -c1-200
for i in $(seq 1 24); do grep -q "OUT_END\|Traceback" /tmp/dz_qa_out.txt 2>/dev/null && break; sleep 10; done
grep -v "^B64" /tmp/dz_qa_out.txt | grep "OUT\|Error\|errs" | cut -c1-500 | sed 's/^/OUT: /' | tail -30
