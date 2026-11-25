echo "C300: k_chk7"
cat /workspace/nox/agent/out/k_orch_bg.log
grep -c MOCKQA /workspace/nox/advisors/gateway.py; grep -c P3_PRIVATE /workspace/nox/advisors/gateway.py
ls /workspace/nox/state/mock_qa | head -3
curl -s -m 60 -X POST http://127.0.0.1:8793/v1/images/critique -H 'Content-Type: application/json' -d '{"image_path":"/workspace/nox/state/mock_qa/chat_1440.jpg","prompt":"test","x_nox_allow_image":true}' | head -c 200; echo
