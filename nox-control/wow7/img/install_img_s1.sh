#!/usr/bin/env bash
# IMG-01 install_img_s1: сервис генерации изображений на S1 (#S1). Идемпотентен. Ничего не останавливает и не перезапускает.
# Использование: install_img_s1.sh [--dry-run] [--models main,fast] [--source hf|pc] [--store DIR] [--no-venv] [--no-weights] [--no-sha] [--skip-tests] [--apply-dsp]
#   --source hf : huggingface_hub (HF_HUB_ENABLE_HF_TRANSFER=1);  --source pc : rsync с «тёплого склада» ПК по Tailscale (NOX_PC_HOST, NOX_PC_IMG_DIR)
# Env: NOX_HOME (/root/nox) SRC (каталог с файлами IMG; по умолчанию рядом) NOX_CTL (репо nox-control) NOX_IMG_MODEL_DIR (куда класть веса)
# Место: веса Chroma1-HD ~30 ГБ + Z-Image-Turbo ~24 ГБ (bf16, оценка: проверить размер на странице модели). Диск S1 тесный, /dev/shm занят GLM:
#   скрипт НЕ качает, если места нет, и честно печатает, куда положить (--store). Веса в рабочем режиме живут в RAM процесса img, не на диске.
set -euo pipefail
DRY=0; MODELS="main,fast"; SOURCE=hf; STORE=""; VENV=1; WEIGHTS=1; SHA=1; TESTS=1; DSP=0
while [ $# -gt 0 ]; do case "$1" in
  --dry-run) DRY=1;; --models) MODELS="$2"; shift;; --source) SOURCE="$2"; shift;; --store) STORE="$2"; shift;;
  --no-venv) VENV=0;; --no-weights) WEIGHTS=0;; --no-sha) SHA=0;; --skip-tests) TESTS=0;; --apply-dsp) DSP=1;;
  *) echo "неизвестный флаг $1" >&2; exit 2;; esac; shift; done
H="${NOX_HOME:-/root/nox}"; CTL="${NOX_CTL:-$H/repo/nox-control}"; SRC="${SRC:-$(cd "$(dirname "$0")" && pwd)}"
STORE="${STORE:-${NOX_IMG_MODEL_DIR:-$H/dl/hf/img}}"; RC="$H/receipts"; VENV_DIR="$H/venv_img"
FILES="img_service.py policy_hard.py prompt_master.py vram_coord.py brain_img.py"
declare -A REPO=( [main]="lodestones/Chroma1-HD" [fast]="Tongyi-MAI/Z-Image-Turbo" )
declare -A DIRN=( [main]="Chroma1-HD" [fast]="Z-Image-Turbo" )
declare -A NEED=( [main]=32 [fast]=26 )
run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else eval "$@"; fi; }
note() { echo "== $*"; }
STEPS=()

note "1. проверка окружения"
command -v python3 >/dev/null || { echo "нужен python3" >&2; exit 1; }
for f in $FILES; do [ -f "$SRC/$f" ] || { echo "нет файла $SRC/$f" >&2; exit 1; }; python3 -c "import ast,sys;ast.parse(open(sys.argv[1]).read())" "$SRC/$f" || { echo "$f: синтаксис" >&2; exit 1; }; done
GPU="нет nvidia-smi"; command -v nvidia-smi >/dev/null && GPU=$(nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader | head -1 || true)
MEMG=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo 2>/dev/null || echo 0)
echo "GPU: $GPU | RAM доступно: ${MEMG} ГБ"
[ "$MEMG" -ge 70 ] 2>/dev/null || echo "ВНИМАНИЕ: RAM доступно <70 ГБ (нужно ~28+21 ГБ весов + запас 48 ГБ диспетчера)"
STEPS+=("preflight")

note "2. venv: torch cu128 (Blackwell sm_120 требует CUDA 12.8+) + diffusers из исходников (ZImagePipeline)"
if [ "$VENV" = 1 ]; then
  run "python3 -m venv '$VENV_DIR'"
  run "'$VENV_DIR/bin/pip' install -q --upgrade pip"
  run "'$VENV_DIR/bin/pip' install -q torch torchvision --index-url https://download.pytorch.org/whl/cu128"
  run "'$VENV_DIR/bin/pip' install -q git+https://github.com/huggingface/diffusers transformers accelerate sentencepiece safetensors protobuf pillow huggingface_hub hf_transfer"
  run "'$VENV_DIR/bin/python' -c \"import torch;print('torch',torch.__version__,'cuda',torch.version.cuda,'arch',torch.cuda.get_arch_list() if torch.cuda.is_available() else 'нет GPU')\""
  STEPS+=("venv")
fi

note "3. веса -> $STORE (источник: $SOURCE)"
WEIGHT_INFO=""
if [ "$WEIGHTS" = 1 ]; then
  run "mkdir -p '$STORE'"
  P="$STORE"; while [ ! -d "$P" ] && [ "$P" != "/" ]; do P=$(dirname "$P"); done
  FREE=$(df -P -BG "$P" 2>/dev/null | awk 'NR==2{gsub("G","",$4);print $4}' || true); FREE="${FREE:-0}"
  TOTAL=0
  for m in ${MODELS//,/ }; do [ -n "${REPO[$m]:-}" ] || { echo "неизвестная роль $m (main|fast)" >&2; exit 2; }; TOTAL=$((TOTAL+${NEED[$m]})); done
  echo "нужно ~${TOTAL} ГБ, свободно ${FREE} ГБ"
  if [ "$FREE" -lt "$TOTAL" ] && [ "$DRY" = 0 ]; then
    echo "МЕСТА НЕТ, веса не скачаны. Варианты: --store <каталог с местом> (затем NOX_IMG_MODEL_DIR), --models fast (меньше), или положить веса на тёплый склад ПК и --source pc с --store на смонтированный диск." >&2
    WEIGHT_INFO="no_space"
  else
    for m in ${MODELS//,/ }; do
      D="$STORE/${DIRN[$m]}"
      if [ -f "$D/model_index.json" ]; then echo "уже есть: $D"; continue; fi
      if [ "$SOURCE" = pc ]; then
        : "${NOX_PC_HOST:?задайте NOX_PC_HOST (Tailscale-имя ПК)}"; : "${NOX_PC_IMG_DIR:?задайте NOX_PC_IMG_DIR (папка с весами на ПК)}"
        run "rsync -a --partial --info=progress2 -e 'ssh -o StrictHostKeyChecking=accept-new' '$NOX_PC_HOST:$NOX_PC_IMG_DIR/${DIRN[$m]}/' '$D/'"
      else
        run "HF_HUB_ENABLE_HF_TRANSFER=1 '$VENV_DIR/bin/python' -c \"from huggingface_hub import snapshot_download as s; s('${REPO[$m]}', local_dir='$D')\""
      fi
      [ "$DRY" = 1 ] || [ -f "$D/model_index.json" ] || { echo "после загрузки нет $D/model_index.json" >&2; exit 1; }
    done
    if [ "$SHA" = 1 ]; then run "(cd '$STORE' && find . -type f \\( -name '*.safetensors' -o -name 'model_index.json' \\) -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)"; fi
    WEIGHT_INFO="ok"
  fi
  STEPS+=("weights:$WEIGHT_INFO")
fi

note "4. код -> $CTL/imagegen (расширение существующего imagegen: server.py/policy.py/judge.py/tool.py не трогаем)"
run "mkdir -p '$CTL/imagegen'"
for f in $FILES; do run "install -m 0644 '$SRC/$f' '$CTL/imagegen/$f'"; done
STEPS+=("code")

note "5. реестр диспетчера (local.json add_services; обновления services.json его не затирают)"
if [ "$DSP" = 1 ]; then
  if [ "$DRY" = 1 ]; then echo "[dry-run] merge $SRC/dsp_patch.json -> $H/dsp/local.json (add_services, protected)"; else
  python3 - "$H/dsp/local.json" "$SRC/dsp_patch.json" <<'PY'
import json, os, sys
lp, pp = sys.argv[1], sys.argv[2]
loc = json.load(open(lp)) if os.path.isfile(lp) else {}
patch = json.load(open(pp))
add = loc.setdefault("add_services", [])
add[:] = [s for s in add if s.get("name") != "img"] + patch["services_add"]
os.makedirs(os.path.dirname(lp), exist_ok=True)
json.dump(loc, open(lp, "w"), ensure_ascii=False, indent=1)
print("img добавлен в", lp, "(перезапуск диспетчера не делаю: он подхватит при следующем старте)")
PY
  fi
  STEPS+=("dsp_local_json")
else echo "пропущено (--apply-dsp)"; fi
echo "хук lease (3 строки в nox_dispatcher.py) описан в dsp_patch.json -> dispatcher_hook; без него работает режим group"

note "6. офлайн-тесты (фейковый движок, без GPU)"
if [ "$TESTS" = 1 ] && [ -f "$SRC/test_img_service.py" ]; then
  run "(cd '$SRC' && python3 -W ignore -m unittest test_policy_hard test_img_service 2>&1 | tail -3)"
  STEPS+=("tests")
fi

note "7. квитанция IMG-01"
REC="$RC/IMG-01.json"
if [ "$DRY" = 1 ]; then echo "[dry-run] запись $REC: шаги=${STEPS[*]} weights=${WEIGHT_INFO:-skipped} store=$STORE gpu=$GPU"; else
  mkdir -p "$RC"
  python3 - "$REC" "$STORE" "$WEIGHT_INFO" "${STEPS[*]}" "$GPU" "$MODELS" <<'PY'
import json, os, sys, time, hashlib
rec, store, w, steps, gpu, models = sys.argv[1:7]
files = {}
for root, _, fs in os.walk(store):
    for f in fs:
        if f == "model_index.json" or f == "SHA256SUMS":
            p = os.path.join(root, f)
            files[os.path.relpath(p, store)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
json.dump({"id": "IMG-01", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "ok": w in ("ok", ""), "weights": w or "skipped", "steps": steps.split(), "store": store,
           "models": models, "gpu": gpu, "sha256": files}, open(rec, "w"), ensure_ascii=False, indent=1)
print("квитанция", rec)
PY
fi
echo "готово. Запуск: $VENV_DIR/bin/python $CTL/imagegen/img_service.py  (или через диспетчер: --apply-dsp). Проверка: curl -s 127.0.0.1:8097/status"
