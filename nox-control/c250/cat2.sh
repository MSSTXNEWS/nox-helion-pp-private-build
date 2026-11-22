#!/bin/bash
cd /root/nox/dl/v7/exec/nox_wow
wc -c SPD/* ../nox_wow/../* 2>/dev/null | head -20; ls /root/nox/dl/v7/exec /root/nox/dl/v7/exec/OPT 2>/dev/null|head -30
for f in SPD/recon_s1.sh SPD/start_glm_best.sh SPD/matrix.json SPD/soul_kv_warm.sh; do echo "=== $f"; cat $f; done
