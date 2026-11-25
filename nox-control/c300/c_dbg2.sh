echo "C300: c_dbg2"
N=/workspace/nox
cut -c1-170 $N/state/c_fix3.out | grep -v "^+" | tail -12
curl -s -m3 localhost:18217/quota; echo; tail -6 $N/state/pipe_err.log | cut -c1-200
curl -s -m10 localhost:8793/v1/models | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d['data']),sum(1 for m in d['data'] if m.get('available') and m.get('status')=='ok' and not m.get('needs_key')));print(d.get('usage'))" 2>&1 | cut -c1-600
curl -s -m20 localhost:18217/fast -d '{"q":"Столица Италии?"}' | cut -c1-300; echo
tail -5 $N/svc/pipeline/pipeline.log | cut -c1-250
