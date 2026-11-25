echo "C300: a2_collect11"
cat /workspace/nox/agents/chatload.log; curl -s -m5 127.0.0.1:8793/v1/chat_metric; echo
grep -c MOCKQA /workspace/nox/advisors/gateway.py; grep -c P3_PRIVATE /workspace/nox/advisors/gateway.py
