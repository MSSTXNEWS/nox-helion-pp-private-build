#!/bin/bash
hostname; nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv,noheader; nproc; free -g | sed -n 2p; df -h / /dev/shm | tail -2
lscpu | grep -E "Model name|NUMA node\(s\)"; cat /sys/fs/cgroup/cpu.max 2>/dev/null
ls /root /workspace 2>/dev/null | head -20 | tr '\n' ' '; echo; ls /root/nox 2>/dev/null | head | tr '\n' ' '
uptime; which python3 git cmake nvcc 2>/dev/null | tr '\n' ' '
