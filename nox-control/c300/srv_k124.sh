echo "C300: srv_k124"
cd /workspace/nox; date -u +%T; grep -v "Loading weights\|Warning\|warn" ops/dpo/run5.log | tail -n 14 | cut -c1-180; df -h /workspace | tail -1; ls models/gpu/bartowski models/gpu/unsloth | head; wc -l ops/teacher_answers/*.jsonl; ls -la STOP; pgrep -fa "quant4|after_dump|chain5" | cut -c1-90
