echo "C300: srv_k126"
cd /workspace/nox; tail -c 2500 ops/dpo/run5.log | tr '\r' '\n' | grep -v "^\s*$" | tail -n 14 | cut -c1-220
grep -n "SystemExit\|sys.exit\|exit" ops/dpo/quant4.py | head; dmesg 2>/dev/null | tail -3 | cut -c1-150; free -g | sed -n 2p
