cd /workspace/nox; setsid nohup /workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py > /tmp/fx_qa.out 2>&1 < /dev/null &
sleep 2; echo started
