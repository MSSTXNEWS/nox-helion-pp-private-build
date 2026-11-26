echo "C300: srv_k22"
cd /workspace/nox
grep -n "distill_v2.py\|gates\|ckpt_guard\|NOX_TRAIN_PHASE\|speed.json\|STOP" agent/autotrain/autotrain.sh | sed -n '1,45p' | cut -c1-260
grep -n "def cmd_gates\|\"gates\"\|add_parser\|--gates\|def gates\|def run_gates" distill_v2/code/distill_v2.py agent/ckpt_guard.py | head -15 | cut -c1-200
curl -s -m 20 "https://datasets-server.huggingface.co/first-rows?dataset=DataCreatorAI/Anti-Sycophancy-DPO&config=default&split=train" | head -c 900; echo
curl -s -m 20 "https://datasets-server.huggingface.co/size?dataset=DataCreatorAI/Anti-Sycophancy-DPO" | head -c 300; echo
head -c 500 state/p3/eval/cases.jsonl; wc -l state/p3/eval/cases.jsonl
