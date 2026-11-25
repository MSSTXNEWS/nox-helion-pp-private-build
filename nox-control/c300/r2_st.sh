cd /workspace/nox/web/site/qa
date; df -h /workspace | tail -1
ls -lat --time-style=+%d%H:%M rework | head -30
tail -4 /tmp/s5_chain4.log
echo ---; python3 - <<'P'
import json,glob
for f in sorted(glob.glob('rework/*.json')):
    try: d=json.load(open(f))
    except Exception as e: continue
    print(f[7:-5], d.get('status'), json.dumps(d.get('s5_auto'),ensure_ascii=False)[:220])
P
echo ---; head -30 summary.md
