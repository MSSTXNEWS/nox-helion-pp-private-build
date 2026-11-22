#!/usr/bin/env bash
# Воспроизводит интеграцию на копии клона в /tmp (в клон ничего не пишет): патчи -> все тесты.
set -euo pipefail
INT="$(cd "$(dirname "$0")" && pwd)"; REPO="${NOX_REPO_ROOT:-/home/claude/msstxnews/nox-helion-pp-private-build}"; W="${NOX_WOW_SRC:-/home/claude/nox_wow}"
T="$(mktemp -d /tmp/int_run.XXXXXX)"; mkdir -p "$T/nox-control"
for s in glm53 qs6 community bridge; do mkdir -p "$T/nox-control/$s"; (cd "$REPO/nox-control/$s" && tar cf - --exclude=__pycache__ --exclude='*.pyc' .) | tar xf - -C "$T/nox-control/$s"; done
cd "$T"; for d in gateway_prime mem_patch per_memory_layer con_bridge; do patch -p1 -s -i "$INT/$d.diff"; done
G="$T/nox-control/glm53"; cp "$W/PRIME/"{gateway_prime.py,nox_prime.py,soul_prime_v3.txt} "$INT/test_gateway_prime.py" "$G/"
mkdir -p "$T/nox-control/wow7/mem" "$T/nox-control/wow7/per" "$T/nox-control/bridge"; cp "$W/MEM/"{memcommon,correction,provenance,consolidate,autobio,life_journal}.py "$T/nox-control/wow7/mem/"
mkdir -p "$T/nox-control/wow7/common"; cp "$W/COMMON/"{statefile,quiet,fastq,datafence,lifelink}.py "$T/nox-control/wow7/common/"; cp "$INT/con_hooks.py" "$T/nox-control/bridge/"; cp "$INT/per/"{perpath,per_wire}.py "$T/nox-control/wow7/per/"
export PYTHONDONTWRITEBYTECODE=1 NOX_WOW_SRC="$W"
export NOX_WOW7_MEM="$T/nox-control/wow7/mem"
for d in qs6 glm53; do (cd "$T/nox-control/$d" && for t in test_*.py; do python3 -W ignore -m unittest "${t%.py}" 2>&1 | tail -1 | sed "s#^#$d/$t PRIME=0 #"; done); done
(cd "$G" && NOX_PRIME=1 python3 -W ignore -m unittest test_gateway_prime 2>&1 | tail -1 | sed 's#^#glm53/test_gateway_prime PRIME=1 #')
unset NOX_WOW7_MEM
(cd "$INT" && for t in test_con_hooks test_int_mem; do python3 -B -W ignore -m unittest $t 2>&1 | tail -1 | sed "s#^#$t #"; done; cd per && python3 -B -W ignore -m unittest test_int_per 2>&1 | tail -1 | sed 's#^#test_int_per #')
echo "workdir: $T"
