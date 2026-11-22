#!/usr/bin/env bash
# SLP-04 train_lora_s2.sh — ночное обучение LoRA спинного мозга на S2 (2xV100 32 ГБ, fp16, без bf16).
# Шаги: проверка GPU/диска/пакетов -> accelerate launch train_kto_s2.py (KTO|SFT) -> LoRA→GGUF (llama.cpp) -> квитанция /root/nox/receipts/SLP-04.json.
# Запуск:  bash train_lora_s2.sh --data DIR --out DIR [--mode kto|sft] [--base Qwen/Qwen3-8B] [--gpus 0,1] [--dry-run]
# Зависимости (pip, на S2): torch>=2.6 (cu12x), trl>=1.18, peft>=0.22, transformers>=5, accelerate>=1.11, datasets>=4.7. Для GGUF: /root/nox/llama.cpp (convert_lora_to_gguf.py).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ID="${SLP_RECEIPT_ID:-SLP-04}"; RECEIPTS="${RECEIPTS_DIR:-/root/nox/receipts}"
BASE="Qwen/Qwen3-8B"; DATA=""; OUT=""; MODE="kto"; GPUS="0,1"; DRY=0; MIN_FREE_MIB="${MIN_FREE_MIB:-26000}"; MIN_DISK_GB="${MIN_DISK_GB:-60}"
LLAMA="${LLAMA_CPP:-/root/nox/llama.cpp}"; SKIP_GGUF=0; EXTRA=()
while [ $# -gt 0 ]; do case "$1" in
  --base) BASE="$2"; shift 2;; --data) DATA="$2"; shift 2;; --out) OUT="$2"; shift 2;; --mode) MODE="$2"; shift 2;;
  --gpus) GPUS="$2"; shift 2;; --dry-run) DRY=1; shift;; --skip-gguf) SKIP_GGUF=1; shift;; --llama-cpp) LLAMA="$2"; shift 2;;
  --epochs|--lr|--beta|--rank|--alpha|--batch|--accum|--max-length|--max-steps) EXTRA+=("$1" "$2"); shift 2;;
  -h|--help) sed -n 2,8p "$0"; exit 0;; *) echo "неизвестный аргумент: $1" >&2; exit 2;; esac; done
[ -n "$DATA" ] && [ -n "$OUT" ] || { echo "нужны --data и --out" >&2; exit 2; }
case "$MODE" in kto|sft) ;; *) echo "--mode kto|sft" >&2; exit 2;; esac

T0=$(date +%s); STATUS="fail"; NOTE=""; CHECKS=""
receipt() {  # JSON безопасно собирает python
  mkdir -p "$RECEIPTS" 2>/dev/null || RECEIPTS="/tmp/nox_receipts" && mkdir -p "$RECEIPTS"
  python3 - "$RECEIPTS/$ID.json" "$STATUS" "$NOTE" "$CHECKS" "$DRY" "$BASE" "$MODE" "$DATA" "$OUT" "$GPUS" "$T0" <<'PY'
import json,sys,time
p,st,note,chk,dry,base,mode,data,out,gpus,t0=sys.argv[1:12]
json.dump({"id":"SLP-04","status":st,"note":note,"checks":[c for c in chk.split("|") if c],"dry_run":dry=="1","base":base,"mode":mode,"data":data,"out":out,"gpus":gpus,
 "started":int(t0),"finished":int(time.time()),"seconds":int(time.time())-int(t0),"host":__import__("socket").gethostname()},open(p,"w"),ensure_ascii=False,indent=1)
print("квитанция:",p)
PY
}
trap 'receipt' EXIT
fail() { NOTE="$1"; echo "ОШИБКА: $1" >&2; exit 1; }
ok() { CHECKS="$CHECKS|$1"; echo "ok: $1"; }

[ -f "$DATA/kto_train.jsonl" ] && [ -f "$DATA/stats.json" ] || fail "нет $DATA/kto_train.jsonl или stats.json (запустите build_kto.py)"
ok "данные найдены"
python3 -I -c "import json,sys;s=json.load(open(sys.argv[1]));sys.exit(0 if s.get('mode') in ('kto','sft') else 3)" "$DATA/stats.json" || fail "stats.mode=skip: ночь без обучения (мало данных)"
ok "режим данных допускает обучение"

# --- GPU: число, свободная память, чужие процессы
if command -v nvidia-smi >/dev/null 2>&1; then
  IFS=',' read -ra G <<<"$GPUS"
  for i in "${G[@]}"; do
    FREE=$(nvidia-smi -i "$i" --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
    NAME=$(nvidia-smi -i "$i" --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    [ -n "$FREE" ] || fail "GPU $i не найден"
    [ "$FREE" -ge "$MIN_FREE_MIB" ] || fail "GPU $i: свободно ${FREE} МиБ < ${MIN_FREE_MIB} (занята другим процессом?)"
    ok "GPU $i ($NAME) свободно ${FREE} МиБ"
  done
else
  [ "$DRY" = 1 ] && ok "nvidia-smi нет (dry-run: проверка GPU пропущена)" || fail "nvidia-smi не найден — это не S2"
fi
# --- диск
AV=$(df -BG --output=avail "$(dirname "$OUT")" 2>/dev/null | tail -1 | tr -dc 0-9); [ -z "$AV" ] && AV=0
[ "$DRY" = 1 ] || [ "$AV" -ge "$MIN_DISK_GB" ] || fail "диск: свободно ${AV} ГБ < ${MIN_DISK_GB}"
ok "диск ${AV} ГБ"
# --- пакеты и fp16
if [ "$DRY" = 0 ]; then
  python3 - <<'PY' || fail "нет пакетов/CUDA: pip install 'trl>=1.18' 'peft>=0.22' 'transformers>=5' accelerate datasets; torch с CUDA"
import torch, trl, peft, transformers, accelerate, datasets
assert torch.cuda.is_available(), "CUDA недоступна"
print("torch", torch.__version__, "trl", trl.__version__, "peft", peft.__version__, "tf", transformers.__version__, "gpus", torch.cuda.device_count())
PY
  ok "пакеты и CUDA"
fi

NPROC=$(awk -F, '{print NF}' <<<"$GPUS")
CMD=(python3 "$HERE/train_kto_s2.py" --base "$BASE" --data "$DATA" --out "$OUT" --mode "$MODE" --gpus "$GPUS" "${EXTRA[@]}")
if [ "$NPROC" -gt 1 ]; then CMD=(accelerate launch --num_processes "$NPROC" --mixed_precision fp16 --dynamo_backend no "${CMD[@]:1}"); CMD=("${CMD[@]}"); fi
if [ "$DRY" = 1 ]; then
  echo "DRY-RUN команда: CUDA_VISIBLE_DEVICES=$GPUS ${CMD[*]} --dry-run"
  python3 "$HERE/train_kto_s2.py" --base "$BASE" --data "$DATA" --out "$OUT" --mode "$MODE" --gpus "$GPUS" "${EXTRA[@]}" --dry-run || fail "dry-run train_kto_s2.py упал"
  [ "$SKIP_GGUF" = 1 ] || echo "DRY-RUN GGUF: python3 $LLAMA/convert_lora_to_gguf.py --base-model-id $BASE --outfile $OUT/adapter-f16.gguf --outtype f16 $OUT/peft"
  STATUS="dry-run-ok"; NOTE="ничего не запускалось на GPU"; exit 0
fi

mkdir -p "$OUT"
export CUDA_VISIBLE_DEVICES="$GPUS" TOKENIZERS_PARALLELISM=false PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
echo "СТАРТ: ${CMD[*]}"
"${CMD[@]}" 2>&1 | tee "$OUT/train.log"; RC=${PIPESTATUS[0]}
[ "$RC" = 0 ] || fail "обучение завершилось с кодом $RC (см. $OUT/train.log)"
[ -f "$OUT/peft/adapter_model.safetensors" ] || fail "адаптер не сохранён (NaN-защита?)"
ok "обучение завершено, адаптер сохранён"
if [ "$SKIP_GGUF" = 0 ]; then
  [ -f "$LLAMA/convert_lora_to_gguf.py" ] || fail "нет $LLAMA/convert_lora_to_gguf.py"
  python3 "$LLAMA/convert_lora_to_gguf.py" --base-model-id "$BASE" --outfile "$OUT/adapter-f16.gguf" --outtype f16 "$OUT/peft" >"$OUT/gguf.log" 2>&1 || fail "конвертация в GGUF не удалась (см. $OUT/gguf.log)"
  [ -s "$OUT/adapter-f16.gguf" ] || fail "пустой GGUF"
  ok "GGUF: $OUT/adapter-f16.gguf"
fi
STATUS="ok"; NOTE="адаптер готов как кандидат; принятие — только после fidelity_test"; exit 0
