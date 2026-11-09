#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/workspace/nox
POD_ID=rsjmb616w0tqio
TOOLS="$ROOT/tools"
LOG="$ROOT/logs"
STAGE="$ROOT/checkpoints/nox_genesis_stage0"
TRAIN_URL="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/570c9d122d6f254a075cd28c41614ebc40110d4f/nox_runpod/stage0/train_original_embryo.py"
mkdir -p "$TOOLS" "$LOG" "$STAGE"
on_exit() {
  local code=$?
  trap - EXIT
  echo "NOX_CYCLE_EXIT code=$code; attempting Pod compute stop" | tee -a "$LOG/nox_genesis_autostop.log"
  sync
  if command -v runpodctl >/dev/null 2>&1; then
    runpodctl pod stop "$POD_ID" >>"$LOG/nox_genesis_autostop.log" 2>&1 || echo "AUTOSTOP_FAILED - manual stop required" >>"$LOG/nox_genesis_autostop.log"
  else
    echo "AUTOSTOP_FAILED - runpodctl unavailable" >>"$LOG/nox_genesis_autostop.log"
  fi
  exit "$code"
}
trap on_exit EXIT
trap 'exit 130' INT TERM
test "$(df -P /workspace | tail -n 1 | awk '{print $6}')" = /workspace || { echo "HOLD: persistent /workspace missing"; exit 11; }
test -s "$ROOT/embryo/NOX_EMBRYO_TRANSFER_STAGE/embryo_manifest.json" || { echo "HOLD: original NOX Embryo missing"; exit 12; }
test -s "$ROOT/models/NOX_PRIME_9B_INHERITED/transfer_manifest.json" || { echo "HOLD: 9B source missing"; exit 13; }
DATA="$ROOT/distillation/embryo_v1/9b_teacher_corpus.jsonl"
test -s "$DATA" || { echo "HOLD: 9B teacher corpus missing"; exit 14; }
command -v runpodctl >/dev/null || { echo "HOLD: no RunPod CLI for autostop"; exit 15; }
# Pod-scoped credentials may forbid GET. Do not block learning solely on it.
if ! runpodctl pod get "$POD_ID" >/dev/null 2>&1; then
  echo 'WARN: Pod-scoped CLI GET unavailable; external scheduled safety stop is armed.'
fi
PY="$ROOT/genesis-venv/bin/python"
test -x "$PY" || { echo "HOLD: existing training environment missing"; exit 17; }
curl -fLsS --retry 3 "$TRAIN_URL" -o "$TOOLS/train_original_embryo.py.new"
"$PY" -m py_compile "$TOOLS/train_original_embryo.py.new"
mv -f "$TOOLS/train_original_embryo.py.new" "$TOOLS/train_original_embryo.py"
P1="$STAGE/pass1"; P2="$STAGE/pass2"; P3="$STAGE/pass3"
mkdir -p "$P1" "$P2" "$P3"
echo "NOX_GENESIS_3PASS_BEGIN"
train_pass() {
  local dir="$1" rate="$2" resume_path="${3:-}"
  local attempt=1 rc=0
  if [ -s "$dir/stage0_receipt.json" ] && [ -s "$dir/embryo_stage0_trained.safetensors" ]; then
    echo "PASS_ALREADY_SAVED $dir"
    return 0
  fi
  while [ "$attempt" -le 3 ]; do
    echo "NOX_PASS_ATTEMPT dir=$dir attempt=$attempt"
    local args=(--steps 1000000 --max-epochs 8 --context 128 --out "$dir" --lr "$rate" --checkpoint-every 10)
    if [ -n "$resume_path" ]; then args+=(--resume "$resume_path"); fi
    set +e
    timeout --signal=INT --kill-after=60s 3900s "$PY" -u "$TOOLS/train_original_embryo.py" "${args[@]}"
    rc=$?
    set -e
    if [ "$rc" -eq 0 ]; then return 0; fi
    echo "NOX_TRAIN_FAILED pass=$dir code=$rc attempt=$attempt"
    # Only retry if a valid intermediate state exists. Do not replay model incompatibilities.
    if [ ! -s "$dir/in_progress.pt" ] || [ ! -s "$dir/in_progress.safetensors" ]; then
      echo "NO_RESUMABLE_STATE: stopping rather than repeating unsupported training."
      return "$rc"
    fi
    attempt=$((attempt+1))
    [ "$attempt" -le 3 ] || break
    sleep $((attempt*10))
  done
  return "$rc"
}
train_pass "$P1" 0.00008
test -s "$P1/embryo_stage0_trained.safetensors" && test -s "$P1/stage0_receipt.json" || { echo "PASS1_MISSING_OUTPUT"; exit 18; }
"$PY" - "$P1/stage0_receipt.json" <<'PYCHK'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
assert r["steps"]>=10 and r["parameters_changed"]>0
assert r["holdout_loss_after"]<r["holdout_loss_before"],"No holdout improvement; no second pass"
print("PASS1_VALIDATED_FOR_CONTINUATION",flush=True)
PYCHK
echo "NOX_GENESIS_PASS2_BEGIN"
train_pass "$P2" 0.00003 "$P1/embryo_stage0_trained.safetensors"
test -s "$P2/embryo_stage0_trained.safetensors" && test -s "$P2/stage0_receipt.json" || { echo "PASS2_MISSING_OUTPUT"; exit 19; }
"$PY" - "$P1/stage0_receipt.json" "$P2/stage0_receipt.json" "$STAGE" <<'PYCHK'
import json,sys,pathlib,hashlib,datetime
a=json.load(open(sys.argv[1],encoding="utf-8"))
b=json.load(open(sys.argv[2],encoding="utf-8"))
assert b["steps"]>=10 and b["parameters_changed"]>0
assert b["holdout_loss_after"] < a["holdout_loss_after"],"Second pass did not improve holdout; preserve pass1"
out=pathlib.Path(sys.argv[3])
receipt={"status":"TWO_PASSES_TRAINED_NOT_INDEPENDENTLY_VALIDATED",
 "source":"Original NOX Embryo V1 checkpoint",
 "teacher":"Local Qwen3.5-9B",
 "pass1_sha256":a["checkpoint_sha256"],"pass2_sha256":b["checkpoint_sha256"],
 "holdout_before":a["holdout_loss_before"],"after_pass1":a["holdout_loss_after"],
 "after_pass2":b["holdout_loss_after"],
 "date_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "birth_recorded":False}
(out/"two_pass_result.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False),encoding="utf-8")
print("NOX_TWO_PASSES_TRAINED_NOT_INDEPENDENTLY_VALIDATED",flush=True)
PYCHK
echo "NOX_GENESIS_PASS3_BEGIN"
train_pass "$P3" 0.00001 "$P2/embryo_stage0_trained.safetensors"
test -s "$P3/embryo_stage0_trained.safetensors" && test -s "$P3/stage0_receipt.json" || { echo "PASS3_MISSING_OUTPUT"; exit 20; }
"$PY" - "$P1/stage0_receipt.json" "$P2/stage0_receipt.json" "$P3/stage0_receipt.json" "$STAGE" <<'PYCHK'
import json,sys,pathlib,datetime,hashlib
a,b,c=[json.load(open(p,encoding="utf-8")) for p in sys.argv[1:4]]
assert c["steps"]>=10 and c["parameters_changed"]>0
assert c["holdout_loss_after"] < b["holdout_loss_after"],"Third pass did not improve; preserve pass2"
out=pathlib.Path(sys.argv[4])
receipt={"status":"THREE_PASSES_TRAINED_NOT_INDEPENDENTLY_VALIDATED",
 "teacher":"Local Qwen3.5-9B","student":"Original NOX Embryo V1 checkpoint",
 "pass_sha256":[a["checkpoint_sha256"],b["checkpoint_sha256"],c["checkpoint_sha256"]],
 "losses":[a["holdout_loss_before"],a["holdout_loss_after"],b["holdout_loss_after"],c["holdout_loss_after"]],
 "date_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "birth_recorded":False,"full_teacher_absorption_verified":False}
(out/"three_pass_result.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False),encoding="utf-8")
print("NOX_THREE_PASSES_TRAINED_NOT_INDEPENDENTLY_VALIDATED",flush=True)
PYCHK
echo "NOX_STAGE0_THREE_PASSES_COMPLETE_AND_SAVED"
