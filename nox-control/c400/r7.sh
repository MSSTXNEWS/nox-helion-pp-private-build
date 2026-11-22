#!/bin/bash
python3 -I - <<'PY'
import json
d=json.load(open('/root/nox/state/c400_dry.json'))
print(d['totals']); print(d['rejected_reasons'])
fs=sorted(d['files'],key=lambda f:-(f['facts']+f['episodes']))[:8]
for f in fs: print(f['path'][-70:],f['facts'],f['episodes'],f['profile'],f['updated'],sum(f['rejected'].values()))
print(len(d['files']),'files',len(d['skipped_files']),'skipped'); import collections
print(collections.Counter(s['reason'][:40] for s in d['skipped_files']).most_common(5))
PY
ls /root/nox/memory/backups | grep c400
