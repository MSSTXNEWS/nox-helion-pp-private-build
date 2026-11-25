S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
[ -f $S/creative.html.bak_dz_1 ] || cp $S/creative.html $S/creative.html.bak_dz_1
curl -fsSL "$R/nzj_7.js" -o $S/nox-dz-creative.js || echo FAIL js
curl -fsSL "$R/nzc_7.css" -o $S/nox-dz-creative.css || echo FAIL css
curl -fsSL "$R/dz_creative_7.html" -o $S/creative.html || echo FAIL html
curl -fsSL "$R/dz_qa_7.py" -o /tmp/dz_qa.py || echo FAIL qa
rm -f /tmp/dz_qa_out.txt
PY=/workspace/nox/venv/bin/python
nohup $PY /tmp/dz_qa.py > /tmp/dz_qa_out.txt 2>&1 &
ls -la $S/qa/rework/ | grep -i "about\|creative" | head; head -c 300 $S/qa/rework/about.fixed 2>/dev/null; echo; echo started QA $(md5sum $S/nox-dz-creative.js | cut -c1-8)
