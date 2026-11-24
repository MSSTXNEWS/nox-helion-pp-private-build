cd /workspace/nox; timeout 270 /workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py 2>&1 | cut -c1-330 | head -60
