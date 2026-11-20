#!/bin/bash
echo "== tune.log"; tail -12 /root/nox/logs/tune.log 2>&1
echo "== conf env"; grep -E "^environment" /etc/supervisor/conf.d/nox-ds41-8098.conf | cut -c1-260
echo "== boot script"; iconv -f utf-8 -t ascii//TRANSLIT -c /root/nox/ops/nox_boot_ds41_8098.sh | cut -c1-170 | head -80
echo "== cpu.stat"; cat /sys/fs/cgroup/cpu.stat 2>/dev/null | grep -E "nr_|throttled"; cat /sys/fs/cgroup/cpu.max 2>/dev/null
