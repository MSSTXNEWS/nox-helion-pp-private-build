cd /workspace/nox
df -h /workspace | tail -1
grep -n "argv" qa_audit.py | head
timeout 900 /workspace/nox/venv/bin/python qa_audit.py settings.html 2>&1 | tail -40 | cut -c1-400
