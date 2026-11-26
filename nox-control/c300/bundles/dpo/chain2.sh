#!/bin/bash
# K1: цепочка v2 (GPU уже свободен, STOP стоит): dry на 4 парах -> полный (100 шагов x16) -> ворота -> снять STOP
N=/workspace/nox; D=$N/ops/dpo; L=$D/run.log
trap 'rm -f $N/STOP; echo "$(date -u +%T) chain2: STOP снят" >> $L' EXIT
touch $N/STOP
echo "$(date -u +%T) chain2: dry" >> $L
bash $D/run_dpo.sh dry >> $L 2>&1
if tail -n 5 $L | grep -q "^rc=0"; then echo "$(date -u +%T) chain2: dry OK, полный" >> $L; bash $D/run_dpo.sh >> $L 2>&1; else echo "$(date -u +%T) chain2: dry упал" >> $L; fi
