#!/bin/bash
# SPD-04 soul_kv_warm: «KV души на диск» — мгновенный старт без prefill системного промпта (на CPU-MoE это десятки секунд).
# Ключ файла = sha256(текст души + модель + ctx). Сменилась душа/модель/ctx -> другой файл, старый не подхватится.
# Режимы: auto (restore если файл есть и работает, иначе warm+save) | warm | restore | save
# Требует llama-server с --slot-save-path DIR (его добавляет start_glm_best.sh). Метка #S1.
# Использование: bash soul_kv_warm.sh [--dry-run] [--port 8081] [--soul /root/nox/state/soul_prompt_ru.txt]
#                                      [--dir /root/nox/state/soul_kv] [--slot 0] [--keep 2] [auto|warm|restore|save]
PORT=8081; SOUL=/root/nox/state/soul_prompt_ru.txt; DIR=/root/nox/state/soul_kv; SLOT=0; KEEP=2; MODE=auto; DRY=0
MODEL_ID=${NOX_MODEL_ID:-GLM-5.3-UD-Q4_K_XL}; CTX=${NOX_CTX:-16384}
while [ $# -gt 0 ]; do case "$1" in
  --dry-run) DRY=1;; --port) PORT="$2"; shift;; --soul) SOUL="$2"; shift;; --dir) DIR="$2"; shift;;
  --slot) SLOT="$2"; shift;; --keep) KEEP="$2"; shift;; auto|warm|restore|save) MODE="$1";;
  *) echo "unknown $1" >&2; exit 2;; esac; shift; done
RECEIPTS=${RECEIPTS:-/root/nox/receipts}
[ -f "$SOUL" ] || { echo "нет файла души: $SOUL" >&2; exit 3; }
KEY=$(cat "$SOUL"; printf '%s|%s' "$MODEL_ID" "$CTX"); KEY=$(printf '%s' "$KEY" | sha256sum | cut -c1-16)
FN="soul_${KEY}.bin"
if [ $DRY -eq 1 ]; then
  echo "DRY: mode=$MODE port=$PORT slot=$SLOT file=$DIR/$FN keep=$KEEP"
  echo "DRY: restore -> POST /slots/$SLOT?action=restore {filename:$FN}; проверка пробой chat (system=душа) cache_n>0; иначе warm: chat max_tokens=1 cache_prompt=true + save; удалю старые soul_*.bin сверх $KEEP; квитанция $RECEIPTS/SPD-04.json"
  exit 0
fi
mkdir -p "$DIR" "$RECEIPTS"
python3 - "$PORT" "$SOUL" "$DIR" "$FN" "$SLOT" "$KEEP" "$MODE" "$RECEIPTS" <<'PY'
import glob, json, os, sys, time, urllib.request, urllib.error
port, soul, d, fn, slot, keep, mode, rc = sys.argv[1:9]
keep = int(keep); base = "http://127.0.0.1:" + port
text = open(soul, encoding="utf-8").read()
def post(path, obj, timeout=1800):
    r = urllib.request.Request(base + path, json.dumps(obj).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as x:
        return json.loads(x.read().decode() or "{}")
def probe():
    # тот же префикс, что у боевых чатов: system = душа; хвост (user) другой -> общий префикс берётся из слота
    return post("/v1/chat/completions", {"messages": [{"role": "system", "content": text}, {"role": "user", "content": "Проверка связи."}],
                                         "max_tokens": 1, "temperature": 0, "cache_prompt": True, "id_slot": int(slot)})
t0 = time.time(); rec = {"id": "SPD-04", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "file": os.path.join(d, fn), "mode": mode}
try:
    urllib.request.urlopen(base + "/health", timeout=5).read()
except Exception as e:
    rec.update(ok=False, error="сервер не отвечает: %s" % e); json.dump(rec, open(os.path.join(rc, "SPD-04.json"), "w"), ensure_ascii=False); print(rec["error"]); sys.exit(4)
path = os.path.join(d, fn); used = None
if mode in ("auto", "restore") and os.path.exists(path):
    try:
        post("/slots/%s?action=restore" % slot, {"filename": fn})
        pr = probe(); cached = (pr.get("timings") or {}).get("cache_n", 0) or 0
        rec["restore_probe_cache_n"] = cached; rec["restore_probe_prompt_n"] = (pr.get("timings") or {}).get("prompt_n")
        if cached > 0: used = "restore"
    except Exception as e:
        rec["restore_error"] = str(e)[:200]
if used is None and mode in ("auto", "warm", "save"):
    if mode != "save":
        pr = probe(); rec["warm_prompt_n"] = (pr.get("timings") or {}).get("prompt_n")
    sv = post("/slots/%s?action=save" % slot, {"filename": fn})
    rec["n_saved"] = sv.get("n_saved"); rec["n_written"] = sv.get("n_written"); used = "warm+save" if mode != "save" else "save"
elif used is None:
    rec.update(ok=False, error="restore не удался и режим не позволяет warm"); json.dump(rec, open(os.path.join(rc, "SPD-04.json"), "w"), ensure_ascii=False); print(rec["error"]); sys.exit(5)
olds = sorted(glob.glob(os.path.join(d, "soul_*.bin")), key=os.path.getmtime, reverse=True)
for o in olds[keep:]:
    os.remove(o)
rec.update(ok=True, used=used, seconds=round(time.time() - t0, 1), size_bytes=os.path.getsize(path) if os.path.exists(path) else None, kept=min(len(olds), keep))
json.dump(rec, open(os.path.join(rc, "SPD-04.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps(rec, ensure_ascii=False))
PY
