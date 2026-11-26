echo "C300: srv_k112"
cd /workspace/nox
du -sh models/big 2>/dev/null; find models/big -type f -size +100M -printf "%s %p\n" | sort -rn | awk '{printf "%.1fGB %s\n",$1/1e9,$2}'
echo "--- запущены (argv содержит models/big)"; pgrep -af "models/big" | cut -c1-160
echo "--- lsof"; lsof +D models/big 2>/dev/null | awk 'NR>1{print $1,$2,$9}' | sort -u | head -8
echo "--- конфиги"; for f in serve/llama-swap.yaml state/orch_registry.json; do echo $f; grep -n "models/big\|OpenCode\|Nemotron" $f 2>/dev/null | cut -c1-160 | head -5; done
grep -rIl "models/big" --include=*.py --include=*.sh --include=*.yaml --include=*.json --include=*.conf --include=*.env . 2>/dev/null | grep -v "\.bak\|/venv/" | head -10
echo "--- warm"; find models/warm -type f -size +100M -printf "%s %p\n" | sort -rn | awk '{printf "%.1fGB %s\n",$1/1e9,$2}'
