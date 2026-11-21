#!/usr/bin/env bash
# Шаги 37-38: установка окружения генерации изображений на S1 (идемпотентно).
# Ставит torch (CUDA 12.9, wheel-индекс https://download.pytorch.org/whl/cu129, там только torch 2.8.0; RTX 5060 Ti = Blackwell sm_120 требует cu128+)
# и diffusers в отдельный venv. Проверяет свободное место. Веса НЕ качает никогда: только печатает команду для ручной загрузки.
# Ничего не трогает у GLM-5.3 / Qwen3-4B / /dev/shm. Запуск: bash imagegen_install_s1.sh
# env: NOX_IMG_VENV (/root/nox/imagegen-venv)  NOX_IMG_MODEL_DIR (/root/nox/imagegen-models)
#      NOX_IMG_TORCH=cu129|cu128|cpu (cu129)   NOX_IMG_MIN_LIB_GB (8)   NOX_IMG_WEIGHTS_GB (40)
#      NOX_IMG_DRY_RUN=1 (печатать команды, не выполнять)   NOX_IMG_FAKE_FREE_KB (тестовая подмена свободного места)
set -u
VENV="${NOX_IMG_VENV:-/root/nox/imagegen-venv}"
MODELS="${NOX_IMG_MODEL_DIR:-/root/nox/imagegen-models}"
TORCH_FLAVOR="${NOX_IMG_TORCH:-cu129}"
MIN_LIB_GB="${NOX_IMG_MIN_LIB_GB:-8}"
WEIGHTS_GB="${NOX_IMG_WEIGHTS_GB:-40}"
DRY="${NOX_IMG_DRY_RUN:-0}"
PY="${NOX_IMG_PYTHON:-python3}"

case "$TORCH_FLAVOR" in
  cu129) TORCH_PIN="torch==2.8.0"; TORCH_INDEX="https://download.pytorch.org/whl/cu129" ;;
  cu128) TORCH_PIN="torch==2.8.0"; TORCH_INDEX="https://download.pytorch.org/whl/cu128" ;;
  cpu)   TORCH_PIN="torch==2.8.0"; TORCH_INDEX="https://download.pytorch.org/whl/cpu" ;;
  *) echo "NOX_IMG_TORCH=$TORCH_FLAVOR: допустимо cu129|cu128|cpu" >&2; exit 2 ;;
esac

free_gb() {  # свободно ГБ на ФС ближайшего существующего родителя пути $1
  local p="$1" kb
  while [ ! -e "$p" ] && [ "$p" != "/" ]; do p="$(dirname "$p")"; done
  if [ -n "${NOX_IMG_FAKE_FREE_KB:-}" ]; then kb="$NOX_IMG_FAKE_FREE_KB"; else kb="$(df -Pk "$p" | awk 'NR==2{print $4}')"; fi
  echo $(( kb / 1024 / 1024 ))
}
run() { if [ "$DRY" = "1" ]; then echo "[dry-run] $*"; else "$@"; fi; }

echo "== NOX imagegen install (S1) =="
LIB_FREE="$(free_gb "$VENV")"; W_FREE="$(free_gb "$MODELS")"
echo "свободно для venv ($VENV): ${LIB_FREE} ГБ; для весов ($MODELS): ${W_FREE} ГБ"

# --- 1. библиотеки
HAVE_LIBS=0
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import torch, diffusers, transformers, accelerate, sentencepiece" >/dev/null 2>&1; then HAVE_LIBS=1; fi
if [ "$HAVE_LIBS" = "1" ]; then
  echo "библиотеки: уже установлены, пропускаю"
else
  if [ "$LIB_FREE" -lt "$MIN_LIB_GB" ]; then
    echo "места нет для библиотек: свободно ${LIB_FREE} ГБ, нужно >= ${MIN_LIB_GB} ГБ. Ничего не установлено и не скачано." >&2
    echo "места нет, веса не скачаны"
    exit 3
  fi
  [ -x "$VENV/bin/python" ] || run "$PY" -m venv "$VENV" || exit 1
  export TMPDIR="$(dirname "$VENV")/.pip-tmp"; mkdir -p "$TMPDIR" 2>/dev/null   # не в /dev/shm: он занят моделью GLM
  run "$VENV/bin/python" -m pip install --no-cache-dir --upgrade pip || exit 1
  run "$VENV/bin/python" -m pip install --no-cache-dir "$TORCH_PIN" --index-url "$TORCH_INDEX" --extra-index-url https://pypi.org/simple || exit 1
  run "$VENV/bin/python" -m pip install --no-cache-dir diffusers transformers accelerate safetensors sentencepiece protobuf pillow || exit 1
  rm -rf "$TMPDIR" 2>/dev/null
fi
if [ "$DRY" != "1" ] && [ -x "$VENV/bin/python" ]; then
  "$VENV/bin/python" -c "import torch,diffusers;print('torch',torch.__version__,'cuda',torch.version.cuda,'доступна',torch.cuda.is_available(),'| diffusers',diffusers.__version__)" || echo "проверка импорта не прошла" >&2
fi

# --- 2. веса: только проверка и подсказка, автоматически не качаем
have_weights=0
if [ -d "$MODELS" ] && { ls "$MODELS"/*/model_index.json >/dev/null 2>&1 || ls "$MODELS"/*.safetensors >/dev/null 2>&1; }; then have_weights=1; fi
if [ "$have_weights" = "1" ]; then
  echo "веса: найдены в $MODELS"
elif [ "$W_FREE" -lt "$WEIGHTS_GB" ]; then
  echo "места нет, веса не скачаны (свободно ${W_FREE} ГБ, FLUX.1-schnell в формате diffusers нужно около ${WEIGHTS_GB} ГБ). Освободите место или смонтируйте другой диск и задайте NOX_IMG_MODEL_DIR."
else
  echo "веса не установлены (место есть: ${W_FREE} ГБ). Автоматически не качаю. Вручную:"
  echo "  $VENV/bin/pip install -U 'huggingface_hub[cli]'"
  echo "  $VENV/bin/huggingface-cli download black-forest-labs/FLUX.1-schnell --local-dir $MODELS/FLUX.1-schnell --exclude 'flux1-schnell.safetensors' 'ae.safetensors'"
fi
echo "запуск: NOX_IMG_MODEL_DIR=$MODELS $VENV/bin/python /root/nox/imagegen/server.py   (порт 127.0.0.1:8096)"
exit 0
