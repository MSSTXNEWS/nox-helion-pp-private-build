#!/bin/bash
bash <(curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c251/fetch_v2.sh) 2>&1 | head -4
cd /root/nox/dl/v7/exec2/nox_wow 2>/dev/null || cd /root/nox/dl/v7/exec/nox_wow
echo "--start_glm_best"; grep -vE '^\s*$' SPD/start_glm_best.sh | cut -c1-170 | head -28
echo "--recon head"; grep -E '^#' SPD/recon_s1.sh | head -6 | cut -c1-200
echo "--ab_bench args"; grep -E 'add_argument' SPD/ab_bench.py | cut -c1-140 | head -14
