echo "C300: srv_k15"
cd /workspace/nox
cat state/speed.json | head -c 800; echo
ls -t distill_v2/ | head; ls -t distill_v2/state 2>/dev/null | head
L=$(ls -t distill_v2/*.log distill_v2/logs/*.log agent/autotrain/*.log state/p3/*.out 2>/dev/null | head -3); echo $L
for f in $L; do echo "-- $f"; tail -n 6 $f | cut -c1-260; done
grep -n "r033\|r032\|A/B\|moe_backend" state/p3/ledger.jsonl state/p3/ledger_srv.txt 2>/dev/null | tail -8 | cut -c1-300
sed -n '1,60p' agent/autotrain/autotrain.sh | cut -c1-200
