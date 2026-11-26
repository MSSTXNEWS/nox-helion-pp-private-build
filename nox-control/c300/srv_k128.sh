echo "C300: srv_k128"
cd /workspace/nox; tail -c 6000 ops/dpo/run6.log | tr '\r' '\n' | grep -v "Loading weights\|^\s*$" | tail -n 12 | cut -c1-200
du -sh models/student/Qwen3.6-35B-A3B-bnb4 2>&1; ls models/student/Qwen3.6-35B-A3B-bnb4 | head
