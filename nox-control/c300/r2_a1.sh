cd /workspace/nox
df -h /workspace | tail -1
ls web/site/qa/rework/*.fixed
cat web/site/qa/rework/settings.json | head -c 1500; echo
grep -n "argv" qa_audit.py | head
timeout 900 python3 qa_audit.py settings.html 2>&1 | tail -40 | cut -c1-400
