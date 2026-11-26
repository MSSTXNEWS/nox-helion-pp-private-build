echo "C300: ch_dc38"
grep -E 'AXE|VISION' /workspace/nox/agent/out/dcqa.out | cut -c1-400
