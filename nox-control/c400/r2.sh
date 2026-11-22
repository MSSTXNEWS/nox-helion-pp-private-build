#!/bin/bash
H=/root/nox; C=$(ls -d $H/repo/nox-control $H/src/nox-control 2>/dev/null|head -1); echo CTL=$C
ls $H/state/v7_flags.json && cut -c1-400 $H/state/v7_flags.json
ls $H/receipts | tr '\n' ' ' | cut -c1-500; echo
for f in brain/nox_core.py brain/conscience.py brain/executors.py brain/organs.py opt/semantic_cache.py opt/best_of_n_fast_judge.py prime/soul_prime_v3.txt rte/probe_pv01.py; do
 a=$(sha256sum $C/wow7/$f 2>/dev/null|cut -c1-8); echo "$f live=$a bytes=$(stat -c%s $C/wow7/$f 2>/dev/null)"; done
ls $C/wow7/GENOME $C/wow7/genome 2>&1 | head -3; ls $C/wow7 | tr '\n' ' '; echo
echo "брат in live:"; grep -rc "брат" $C/wow7/brain/*.py $C/wow7/prime/* 2>/dev/null | grep -v ':0'
ps -eo pid,args | grep -E 'nox_core|rte_server|advisor|gateway|8095|semantic' | grep -v grep | cut -c1-150
for p in $(pgrep -f nox_core.py|head -1); do tr '\0' '\n' </proc/$p/environ | grep -E '^NOX_' | head -20; done
ls $H/dl/v7 | head; sha256sum $H/dl/v7/core/nox_wow/BRAIN/nox_core.py | cut -c1-8
