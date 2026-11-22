#!/usr/bin/env bash
# SELF-09 install_music_pc: сервис генерации музыки на ПК/S2 (не S1). Идемпотентен. bash install_music_pc.sh [--dry-run] [--no-weights] [--models musicgen-small,stable-audio-open]
set -euo pipefail
DRY=0; WEIGHTS=1; MODELS="musicgen-small"
while [ $# -gt 0 ]; do case "$1" in --dry-run) DRY=1;; --no-weights) WEIGHTS=0;; --models) MODELS="$2"; shift;; *) echo "неизвестный флаг $1" >&2; exit 2;; esac; shift; done
H="${NOX_HOME:-$HOME/nox}"; SRC="$(cd "$(dirname "$0")" && pwd)"; DEST="$H/src/music"; MD="${NOX_MUSIC_MODEL_DIR:-$H/dl/hf/music}"; V="$H/venv_music"
run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else eval "$@"; fi; }
[ -f "$SRC/music_service.py" ] || { echo "нет music_service.py" >&2; exit 2; }
python3 -c "import ast,sys;ast.parse(open(sys.argv[1]).read())" "$SRC/music_service.py"
run "mkdir -p '$DEST' '$MD' '$H/receipts'"
run "cp '$SRC/music_service.py' '$SRC/test_music_service.py' '$DEST/'"
run "python3 -m venv '$V' && '$V/bin/pip' install -q --upgrade pip && '$V/bin/pip' install -q torch transformers accelerate scipy diffusers soundfile huggingface_hub"
if [ "$WEIGHTS" = 1 ]; then
  for m in ${MODELS//,/ }; do case "$m" in
    musicgen-small) run "'$V/bin/python' -c \"from huggingface_hub import snapshot_download as s; s('facebook/musicgen-small', local_dir='$MD/musicgen-small')\"";;
    stable-audio-open) run "'$V/bin/python' -c \"from huggingface_hub import snapshot_download as s; s('stabilityai/stable-audio-open-1.0', local_dir='$MD/stable-audio-open-1.0')\"  # нужен HF_TOKEN и принятие лицензии";;
    *) echo "неизвестная модель $m" >&2; exit 2;; esac; done
fi
run "cd '$DEST' && python3 -m unittest test_music_service"
echo "Запуск: NOX_MUSIC_HOST=<tailscale-ip> NOX_MUSIC_TOKEN=... $V/bin/python $DEST/music_service.py   (лицензия MusicGen-small CC-BY-NC: личное использование)"
