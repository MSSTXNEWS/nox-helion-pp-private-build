#!/bin/bash
# c91: S1 «МОЗГ» (Vast #61825960, Квебек): только чтение. План v4, этап 2.1
echo "== host"; hostname; uname -r; cat /etc/os-release | grep PRETTY | cut -d= -f2
echo "== GPU"; nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version,compute_cap --format=csv,noheader 2>&1 | head -3
echo "== CPU/RAM"; nproc; lscpu | grep -E "Model name|Thread|Socket|^NUMA node\(s\)|Flags" | sed 's/Flags.*\(avx512[a-z_0-9]*\).*/Flags: avx512 yes/' | cut -c1-90 | head -5; free -g | sed -n 2p
echo "== cgroup mem limit"; cat /sys/fs/cgroup/memory.max 2>/dev/null || cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null
echo "== disk"; df -h / /dev/shm | tail -2
echo "== tools"; for t in python3 pip git cmake gcc g++ nvcc aria2c rsync tailscale supervisorctl hf; do printf "%s=%s " $t "$(command -v $t >/dev/null && echo yes || echo no)"; done; echo; nvcc --version 2>/dev/null | tail -1; python3 --version
echo "== net"; (curl -sS -m 8 -o /dev/null -w "huggingface=%{http_code} " https://huggingface.co/api/models/unsloth/GLM-5.3-GGUF; curl -sS -m 8 -o /dev/null -w "github=%{http_code}\n" https://github.com) 2>&1
echo "== gpu clocks perm"; nvidia-smi -pm 1 2>&1 | head -1
echo "== procs"; ps -eo comm --no-headers | sort | uniq -c | sort -rn | head -6
