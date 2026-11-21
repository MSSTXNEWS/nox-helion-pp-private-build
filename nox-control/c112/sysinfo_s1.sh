#!/bin/bash
grep -iE "system_info|AVX|n_threads|flash|offload|CUDA0|CPU_Mapped|CPU model buffer|KV" /root/nox/logs/glm_server.log | grep -v "unused tensor" | head -14 | cut -c1-260
grep -m1 -o "avx512[a-z_0-9]*" /proc/cpuinfo | sort -u | head -8 | tr '\n' ' '; echo
cat /sys/fs/cgroup/cpu.stat | head -6
