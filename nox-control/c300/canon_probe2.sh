#!/bin/bash
echo "C300: canon_probe2"
N=/workspace/nox
df -h /workspace | tail -1
echo "== du top"
du -xsh $N/* 2>/dev/null | sort -rh | head -14
echo "== du backup/archive"
du -xsh $N/backup/* $N/archive/* 2>/dev/null | sort -rh | head -8
echo "== meta only (no content)"
stat -c '%n %s B mtime=%y' $N/backup/soul_backup_ok.json $N/state/core/genesis_ledger.json $N/agents/passport_prompt.json $N/state/mind/*.json 2>/dev/null | sed 's#/workspace/nox/##' | cut -c1-110 | head -20
python3 - <<'PY'
import json
for p in ['state/core/genesis_ledger.json','state/mind/aliveness.json','state/mind/control_vectors.json','state/mind/morning_brief.json','state/mind/initiative.json']:
    try:
        d=json.load(open('/workspace/nox/'+p)); print(p,type(d).__name__,(sorted(d.keys())[:12] if isinstance(d,dict) else len(d)))
    except Exception as e: print(p,'ERR',type(e).__name__)
PY
echo "born_at files:"; grep -l '"born_at"' $N/state/core/*.json 2>/dev/null | head -3
ls $N/state/core | head -30
echo "== s03/db"; find $N -maxdepth 4 -iname '*.db' -size +10k -not -path '*/venv*' 2>/dev/null | head -12
echo "== procs"; pgrep -af 'life_loop|emo_tick|sleep.py|nox_worms|mind' | cut -c1-110 | head -8
echo "== cron mem/sleep"; crontab -l 2>/dev/null | grep -iE 'backup|sleep|morning|dream' | cut -c1-120
echo "== models"; ls $N/voice_models 2>/dev/null | head; ls $N/models 2>/dev/null | head -30
echo "== data"; ls $N/data | head -25
echo "== RTE"; ls $N/brain/RTE 2>/dev/null | head
