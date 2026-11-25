echo "C300: a2_collect9"
tail -6 /workspace/nox/agents/live6b.log | cut -c1-1100
curl -s -m5 127.0.0.1:8810/metrics | head -c 500; echo
