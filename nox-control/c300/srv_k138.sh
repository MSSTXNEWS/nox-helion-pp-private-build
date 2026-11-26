echo "C300: srv_k138"
cd /workspace/nox; date -u +%T
ss -ltnp 2>/dev/null | grep -E ":(18091|8091|8090|8510|8300|18217|18218|8400) " | awk '{print $4,$6}' | cut -c1-60
grep -rn "api/turn" --include=*.py . 2>/dev/null | grep -v "venv\|\.bak\|vendor\|test_" | cut -c1-170 | head -6
ls -t *.log logs/*.log state/*.log 2>/dev/null | head -0; ls -t web/*.log agent/out/chat*.log 2>/dev/null | head -4
