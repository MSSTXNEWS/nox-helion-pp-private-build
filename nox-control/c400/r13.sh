#!/bin/bash
for d in /root/nox/dl/v7/exec/nox_wow/GENOME /root/nox/dl/v7/core/nox_wow/GENOME; do echo "== $d"; ls -la --time-style=+ $d | awk 'NR>1{print $5,$7}' | head -25; done
echo; ls /root/nox/repo/nox-control/wow7/GENOME 2>&1 | head -2
head -c 900 /root/nox/dl/v7/exec/nox_wow/GENOME/core_adapter.py 2>/dev/null
