#!/usr/bin/env bash
# run_all_tests.sh - гоняет ВСЕ тесты пакета NOX v7: python3 -m unittest в каждой папке + node-тесты + INT/run_all.sh (если есть клон).
# Использование: COMMON/run_all_tests.sh [--no-int]   Код возврата 0 = всё зелёное. Env: NOX_WOW_SRC (корень пакета), NODE (бинарь node).
set -uo pipefail
W="${NOX_WOW_SRC:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
NODE="${NODE:-$(command -v node || echo /opt/node22/bin/node)}"
export PYTHONDONTWRITEBYTECODE=1 NOX_WOW_SRC="$W"
FAIL=0; N=0
ok()  { N=$((N+1)); printf 'OK    %s\n' "$1"; }
bad() { N=$((N+1)); FAIL=$((FAIL+1)); printf 'FAIL  %s\n' "$1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | tail -15 | sed 's/^/      /'; }
for d in COMMON ACT ADV BRAIN CON CTX DSP EMO IMG MEM MIND/M1_ARCH MIND/M2_SELFIMPROVE MIND/M3_CONSCIOUS MIND/M4_BENCH MIND/M5_GROWTH MIND/R2 PER RTE SELF SLP SPD TOP TRAITS WORLD WOW; do
  for t in "$W/$d"/test_*.py "$W/$d"/tests/test_*.py; do
    [ -f "$t" ] || continue
    dd="$(dirname "$t")"; m="$(basename "$t" .py)"
    out="$(cd "$dd" && timeout 600 python3 -W ignore -m unittest "$m" 2>&1)"; rc=$?
    [ $rc -eq 0 ] && ok "$d/$m" || bad "$d/$m" "$out"
  done
done
if [ -x "$NODE" ] || command -v "$NODE" >/dev/null 2>&1; then
  for t in "$W/SELF/test_soundscape.js" "$W/WOW/web/test_presence.js" "$W/MEM/tests/js_ui_test.js"; do
    [ -f "$t" ] || continue
    out="$(cd "$(dirname "$t")" && timeout 300 "$NODE" "$t" 2>&1)"; rc=$?
    [ $rc -eq 0 ] && ok "node $(basename "$t")" || bad "node $(basename "$t")" "$out"
  done
else
  bad "node не найден (NODE=...)"
fi
if [ "${1:-}" != "--no-int" ] && [ -f "$W/INT/run_all.sh" ] && [ -d "${NOX_REPO_ROOT:-/home/claude/msstxnews/nox-helion-pp-private-build}/nox-control" ]; then
  out="$(bash "$W/INT/run_all.sh" 2>&1)"
  if printf '%s' "$out" | grep -E "FAILED|Error|Traceback" >/dev/null; then bad "INT/run_all.sh" "$out"; else ok "INT/run_all.sh"; fi
fi
echo "---- тестов: $N, провалов: $FAIL"
[ $FAIL -eq 0 ]
