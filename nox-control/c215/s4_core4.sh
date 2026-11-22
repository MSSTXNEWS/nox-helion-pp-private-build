#!/bin/bash
# c212 retry S1_04 with v4 brain
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main
rm -rf /tmp/v7deploy; mkdir -p /tmp/v7deploy; curl -fsSL "$B/nox-control/wow7/deploy/S1_04_core.sh?cb=$RANDOM" -o /tmp/v7deploy/S1_04_core.sh
sleep 1; bash /tmp/v7deploy/S1_04_core.sh > /root/nox/logs/V7-04.run.log 2>&1; echo "rc=$?"
tail -c 1800 /root/nox/logs/V7-04.run.log
curl -fsSL "$B/nox-control/c122/boot_s1.sh?cb=$RANDOM" -o /tmp/boot_new.sh && bash -n /tmp/boot_new.sh && grep -q "V7 ФЛАГИ" /tmp/boot_new.sh && { cp -a /root/nox/boot_s1.sh /root/nox/boot_s1.sh.bak-v7 2>/dev/null; cp /tmp/boot_new.sh /root/nox/boot_s1.sh; echo "boot_s1 delivered"; }
cat /root/nox/state/v7_flags.json
