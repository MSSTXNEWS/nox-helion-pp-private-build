#!/usr/bin/env bash
# local_dryrun.sh: проверка этапов V7 ЛОКАЛЬНО без сервера: bash -n всех скриптов + --dry-run каждого этапа в песочнице (V7_HOME во временной папке, ничего не пишется).
# Использование: local_dryrun.sh [каталог со скриптами]   rc 0 = всё ок
D="$(cd "${1:-$(dirname "${BASH_SOURCE[0]}")}" && pwd)"; SB="$(mktemp -d /tmp/v7sb.XXXXXX)"; FAIL=0
export V7_HOME="$SB/nox" V7_RAW="file://$SB/none"
for f in "$D"/lib_v7.sh "$D"/S1_0*.sh; do bash -n "$f" && echo "bash -n OK  $(basename "$f")" || { echo "bash -n FAIL $f"; FAIL=1; }; done
for f in "$D"/S1_0*.sh; do
  out=$(bash "$f" --dry-run 2>&1); rc=$?
  if [ $rc = 0 ] && echo "$out" | grep -q "DRY-RUN готов" && [ ! -e "$SB/nox" ]; then echo "dry-run OK  $(basename "$f") ($(echo "$out" | grep -c '^\[V7-\|^[0-9a-z]') строк)"; else echo "dry-run FAIL $(basename "$f") rc=$rc"; echo "$out" | tail -5; FAIL=1; fi
done
rm -rf "$SB"; exit $FAIL
