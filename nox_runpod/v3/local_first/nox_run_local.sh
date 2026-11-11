#!/usr/bin/env bash
# Deliberately read-only by default. Never starts or stops a GPU worker automatically.
set -euo pipefail
ROOT=${NOX_WORKDIR:-/root/nox_local}
BASE=${BASE:-/dev/shm/base36}
TD=${TD:-$ROOT/data/tok}
SEED=${NOX_SEED_PATH:-$ROOT/seed}
PY=${NOX_PYTHON:-/root/venv/bin/python}
HERE=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $ROOT == /workspace* || $BASE == /workspace* || $TD == /workspace* || $SEED == /workspace* ]]; then
 echo 'HOLD: network path detected; refuses to launch' >&2;exit 2
fi
if [[ ! -x $PY ]];then echo "HOLD: Python missing: $PY" >&2;exit 2;fi
if [[ ! -f $ROOT/scripts/train_n36_local.py ]];then echo 'HOLD: patched local trainer missing' >&2;exit 2;fi
[[ "${1:---check}" == '--run' ]] || {
 echo 'CHECK MODE ONLY. To run, first independently verify input hashes/checkpoint.'
 exec python3 "$HERE/nox_local_preflight.py" --root "$ROOT" --base "$BASE" --data "$TD" \
   --seed "$SEED/common.py" --trainer "$ROOT/scripts/train_n36_local.py" --hash-checkpoint
}
# The actual run is a separate explicit action. No supervisor, kill, reformat or volume IO.
BACKUP_SHA=${NOX_BACKUP_SHA_MANIFEST:-/root/nox_inbox/ckpt_sha256_reference.json}
if [[ ! -f $BACKUP_SHA ]]; then
 echo "HOLD: independent Japanese-backup SHA manifest missing: $BACKUP_SHA" >&2;exit 2
fi
python3 "$HERE/nox_local_preflight.py" --root "$ROOT" --base "$BASE" --data "$TD" \
 --seed "$SEED/common.py" --trainer "$ROOT/scripts/train_n36_local.py" --hash-checkpoint \
 --backup-digest-manifest "$BACKUP_SHA" --json-out "$ROOT/nox-local-preflight.json" >/dev/null || {
 echo 'HOLD: local preflight failed; trainer NOT started' >&2;exit 2;}
if ! python3 -c 'import json,sys;sys.exit(0 if json.load(open(sys.argv[1])).get("externalBackupDigestMatched") is True else 2)' "$ROOT/nox-local-preflight.json";then
 echo 'HOLD: source-server SHA not verified, no new trainer started' >&2;exit 2
fi
if pgrep -af '[/]root/nox_local/scripts/train_n36_local.py|[/]workspace/nox36/scripts/train_n36.py' >/dev/null;then
 echo 'HOLD: another NOX trainer detected. No second process started.' >&2;exit 2
fi
command -v flock >/dev/null || { echo 'HOLD: flock not found' >&2;exit 2; }
exec 9>"$ROOT/nox-local-trainer.lock"
flock -n 9 || { echo 'HOLD: training lease already held' >&2;exit 2; }
export NOX_WORKDIR="$ROOT" BASE="$BASE" TD="$TD" NOX_SEED_PATH="$SEED"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false
export RUN=sft SAVE_MIN=${SAVE_MIN:-15} EVAL=${EVAL:-1}
# Original code resumes from local ckpt/sft/last/STEP, no -f or cleanup.
exec "$PY" "$ROOT/scripts/train_n36_local.py"
