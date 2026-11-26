#!/bin/bash
echo "C300: canon_probe4"
N=/workspace/nox
grep -rln 'dreamer.json' $N/agent $N/brain $N/stewards $N/ops --include=*.py --include=*.sh 2>/dev/null | head -5
F=$N/agent/nox_agents/sleep.py; wc -l $F; stat -c '%y' $F
grep -n 'def \|dreamer\|02:\|hour\|REM\|NREM\|import' $F | cut -c1-150 | head -50
echo "== state/mind dreams"; ls -la --time-style=+%m-%d_%H:%M $N/state/mind | grep -iE 'dream|sleep|night'
ls $N/state | grep -iE 'dream|sleep|night|rem' | head
echo "== supervisor/proc sleep"; supervisorctl status 2>/dev/null | grep -iE 'agents|sleep|dream'; pgrep -af 'nox_agents' | cut -c1-120 | head -5
python3 - <<'PY'
import json
d=json.load(open('/workspace/nox/state/mind/dreamer.json'))
print({k:(type(v).__name__, (len(v) if hasattr(v,'__len__') else v)) for k,v in d.items()})
print('night keys', d.get('night') if isinstance(d.get('night'),(dict,)) and len(str(d.get('night')))<300 else type(d.get('night')).__name__)
PY
