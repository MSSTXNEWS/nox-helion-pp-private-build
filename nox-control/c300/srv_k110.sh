echo "C300: srv_k110"
cd /workspace/nox; cat ops/dpo/run5.log | cut -c1-200 | head -20
ls -la distill_v2/rows_train.jsonl 2>&1; ls distill_v2 | head -30
head -c 600 distill_v2/rows_train.jsonl 2>/dev/null; echo; ls ops/dpo/*.jsonl; head -c 400 ops/dpo/dpo_train.jsonl
ls -la STOP; ls models/gpu/bartowski models/gpu/unsloth 2>&1 | head; rm -f ops/teacher_answers/*.jsonl
