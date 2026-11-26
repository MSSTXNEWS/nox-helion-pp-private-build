echo "C300: srv_k113"
cd /workspace/nox; date -u +%T; tail -n 8 ops/dpo/run5.log | cut -c1-200; wc -l ops/teacher_answers/*.jsonl 2>&1; ls STOP; df -h /workspace|tail -1
