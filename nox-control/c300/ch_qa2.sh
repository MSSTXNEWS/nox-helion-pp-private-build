echo "C300: ch_qa2"
N=/workspace/nox
echo "== q10"; cat $N/state/ch_q10.out | cut -c1-200; pgrep -af q10.py | head -2
cat > /tmp/ch_qa_run.sh <<'X'
while pgrep -f q10.py >/dev/null; do sleep 5; done
cd /workspace/nox; cp web/site/qa/audit.json web/site/qa/audit.json.bak_ch 2>/dev/null
QA_FAST=1 flock /tmp/qaa.lock /workspace/nox/venv/bin/python -I /workspace/nox/qa_audit.py chat.html > /workspace/nox/state/ch_audit1.log 2>&1
python3 -c "import json;json.load(open('/workspace/nox/web/site/qa/audit.json'))" 2>&1 || cp /workspace/nox/web/site/qa/audit.json.bak_ch /workspace/nox/web/site/qa/audit.json
echo DONE >> /workspace/nox/state/ch_audit1.log
X
setsid -f bash /tmp/ch_qa_run.sh < /dev/null > /dev/null 2>&1; echo queued
