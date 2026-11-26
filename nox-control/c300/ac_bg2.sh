echo "C300: ac_bg2"
rm -rf /workspace/nox/tmp/dd; df -h /workspace | tail -1
for P in 8141 8812; do echo "== $P"; grep -rlE "[: ]$P\b" /workspace/nox/stewards/*.py /workspace/nox/judges/*.py /workspace/nox/ops/*.py /workspace/nox/agent/*.py /workspace/nox/stewards/*.json 2>/dev/null | head -8; curl -s -m 3 127.0.0.1:$P/slots | python3 -c "import sys,json;d=json.load(sys.stdin);print([(s.get('id'),s.get('is_processing')) for s in d])" 2>&1 | head -2; ss -tn state established "( sport = :$P )" | wc -l; done
