echo "C300: k_priv1"
ls -la /workspace/nox/advisors/*.log /workspace/nox/advisors/logs 2>/dev/null | head; ls /workspace/nox/state | grep -i -E "gw|gateway|advis" | head
for f in $(ls /workspace/nox/advisors/*.jsonl /workspace/nox/state/advisors*.jsonl /workspace/nox/advisors/logs/*.jsonl 2>/dev/null); do echo "== $f $(wc -l < $f)"; done
/workspace/nox/venv/bin/python - <<'PY'
import json,glob,re,os,datetime
terms=re.compile(r'(иск|суд|суда|судеб|исков|финанс|кредит|долг|здоров|лечени|диагноз|болезн|lawsuit|court|medical)',re.I)
files=glob.glob('/workspace/nox/advisors/**/*.jsonl',recursive=True)+glob.glob('/workspace/nox/state/*advis*.jsonl')
lo=datetime.datetime(2026,11,25,22,50,tzinfo=datetime.timezone.utc).timestamp(); hi=datetime.datetime(2026,11,26,0,30,tzinfo=datetime.timezone.utc).timestamp()
hits=0; total=0
for f in files:
  for ln in open(f,errors='ignore'):
    try: r=json.loads(ln)
    except: continue
    ts=r.get('ts') or r.get('time') or 0
    try: ts=float(ts)
    except: continue
    if not(lo<=ts<=hi): continue
    total+=1
    txt=json.dumps(r,ensure_ascii=False)
    prov=str(r.get('provider') or r.get('model') or r.get('used') or '')
    if terms.search(txt) and not prov.startswith(('lcoder','local','ltrainer','lt-','t-lite')):
      hits+=1; print('HIT', datetime.datetime.utcfromtimestamp(ts).strftime('%H:%M:%S'), prov[:40], (terms.search(txt).group(0)))
print('files',len(files),'records_in_window',total,'external_private_hits',hits)
PY
