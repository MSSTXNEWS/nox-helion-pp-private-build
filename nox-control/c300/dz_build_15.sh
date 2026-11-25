S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
[ -f $S/creative.html.bak_dz_1 ] || cp $S/creative.html $S/creative.html.bak_dz_1
curl -fsSL "$R/nzj_15.js" -o $S/nox-dz-creative.js || echo FAIL js
curl -fsSL "$R/nzc_15.css" -o $S/nox-dz-creative.css || echo FAIL css
curl -fsSL "$R/dz_creative_15.html" -o $S/creative.html || echo FAIL html
curl -fsSL "$R/dz_qa_15.py" -o /tmp/dz_qa.py || echo FAIL qa
pkill -f dz_qa.py; if [ -f $S/nox-ghost.js ] \&\& ! grep -q nox-ghost $S/creative.html; then sed -i 's#<script src="./nox-dz-creative.js#<script src="./nox-ghost.js" defer></script>\n<script src="./nox-dz-creative.js#' $S/creative.html; echo ghost-tag-added; else echo ghost-file-$([ -f $S/nox-ghost.js ] \&\& echo yes || echo no); fi
echo FIXEDFMT; ls -la $S/qa/rework/ | grep -i 'about.fixed\|creative'; head -c 500 $S/qa/rework/about.fixed; echo; head -c 300 $S/qa/rework/creative.fixed; echo; grep -n 'export\|NOXGhost\|window\.' $S/nox-ghost.js 2>/dev/null | head -8
rm -f /tmp/dz_qa_out.txt
PY=/workspace/nox/venv/bin/python
nohup $PY -u /tmp/dz_qa.py > /tmp/dz_qa_out.txt 2>&1 &
ls -la $S/qa/rework/ | grep -i "about\|creative" | head; head -c 300 $S/qa/rework/about.fixed 2>/dev/null; echo; echo started QA $(md5sum $S/nox-dz-creative.js | cut -c1-8)
