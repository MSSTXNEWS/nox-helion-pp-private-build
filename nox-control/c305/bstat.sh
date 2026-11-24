#!/bin/bash
date -u +%T; echo health=$(curl -s -m 5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8081/health)
# Owner diagnostic output is an allowlist, not a raw log or argv export.
# File presence is useful; file names, paths, log text and command arguments are not.
printf 'flash_log_present='; if [ -f /root/nox/logs/flash.log ]; then echo yes; else echo no; fi
printf 'flash_speed_file_present='; if [ -f /root/nox/state/FLASH_SPEED.json ]; then echo yes; else echo no; fi
ps -eo pid=,etimes=,comm= 2>/dev/null | awk '
  NF == 3 && $1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ &&
  ($3 == "llama-server" || $3 == "flash.py") {
    printf "process_pid=%s elapsed_seconds=%s executable=%s\n", $1, $2, $3
  }'
# Read only a bounded regular metrics file. Emit fixed keys and finite numeric
# values, never arbitrary keys, strings, nested objects or parse error details.
if command -v python3 >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
  timeout -k 1s 3s python3 - 2>/dev/null <<'PYFLASH' || echo 'flash_speed_metrics=unavailable'
import json
import math
import os
import stat
try:
    fd = os.open("/root/nox/state/FLASH_SPEED.json",
                 os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("not a regular file")
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError("oversized metrics")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("not an object")
    keys = ("tg", "pp", "ttft", "ttft_s", "tg_tps", "pp_tps",
            "tokens_per_second", "prompt_tokens_per_second",
            "generation_tokens_per_second", "p50_ms", "p95_ms")
    values = []
    for key in keys:
        value = obj.get(key)
        if type(value) in (int, float) and 0 <= value <= 1e9 and math.isfinite(value):
            values.append((key, value))
    if not values:
        raise ValueError("no numeric metrics")
    for key, value in values:
        print("flash_speed_" + key + "=" + str(value))
except (OSError, ValueError, OverflowError, RecursionError):
    print("flash_speed_metrics=unavailable")
PYFLASH
else
  echo 'flash_speed_metrics=unavailable'
fi
# One bounded NVML probe for legacy used-only and detailed telemetry.
# A stalled GPU driver must not stall the owner readback; unknown is never admission.
gpu_rows=''
if command -v nvidia-smi >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
  gpu_rows=$(timeout -k 1s 4s nvidia-smi --query-gpu=index,memory.used,memory.free,memory.total,utilization.gpu --format=csv,noheader,nounits 2>/dev/null) || gpu_rows=''
fi
# Validate the entire GPU snapshot before publishing ANY capacity number.
# A partial or contradictory NVML response must not be mistaken for admission.
if [ -n "$gpu_rows" ]; then
  gpu_rows=$(printf '%s\n' "$gpu_rows" | awk -F, '
    NF != 5 {bad=1; next}
    {
      for (i=1; i<=5; i++) {
        gsub(/[[:space:]]/, "", $i)
        if ($i !~ /^[0-9]+$/) bad=1
      }
      if (seen[$1]++ || $5+0 > 100 || $2+$3 > $4) bad=1
      lines[++n]=$1 "," $2 "," $3 "," $4 "," $5
    }
    END {
      if (bad || n == 0) exit 1
      for (i=1; i<=n; i++) print lines[i]
    }') || gpu_rows=''
fi
if [ -n "$gpu_rows" ]; then
  printf '%s\n' "$gpu_rows" | awk -F, '{print $2 " MiB"}'
else
  echo 'gpu_memory_used=unavailable'
fi

# D2 read-only resource snapshot. No workload probes or host mutations.
echo '== NOX_D2_RESOURCE_SNAPSHOT_V1 =='
printf 'sample_utc='; date -u +%Y-%m-%dT%H:%M:%SZ
printf 'loadavg='; awk '{print $1, $2, $3}' /proc/loadavg
# Bounded 1s host CPU sample: host-wide busy percentage, not cgroup quota admission.
if [ -r /proc/stat ]; then
  read -r _ u1 n1 s1 i1 w1 irq1 sirq1 steal1 rest1 < /proc/stat
  sleep 1
  read -r _ u2 n2 s2 i2 w2 irq2 sirq2 steal2 rest2 < /proc/stat
  if [[ "$u1" =~ ^[0-9]+$ && "$u2" =~ ^[0-9]+$ && "$steal1" =~ ^[0-9]+$ && "$steal2" =~ ^[0-9]+$ ]]; then
    dtotal=$((u2+n2+s2+i2+w2+irq2+sirq2+steal2-u1-n1-s1-i1-w1-irq1-sirq1-steal1))
    didle=$((i2+w2-i1-w1))
    if (( dtotal > 0 && didle >= 0 && didle <= dtotal )); then
      cpu_tenths=$(((dtotal-didle)*1000/dtotal))
      printf 'host_cpu_busy_pct_1s=%d.%d\n' "$((cpu_tenths/10))" "$((cpu_tenths%10))"
    else echo 'host_cpu_busy_pct_1s=unavailable'; fi
  else echo 'host_cpu_busy_pct_1s=unavailable'; fi
else
  echo 'host_cpu_busy_pct_1s=unavailable'
fi
awk '/^MemTotal:|^MemAvailable:/ {printf "%s%s_KiB=%s", (NR==1?"":" "), substr($1,1,length($1)-1), $2} END {print ""}' /proc/meminfo
for k in memory.current memory.max memory.events cpu.stat; do
  p="/sys/fs/cgroup/$k"
  if [ -r "$p" ]; then
    printf 'observer_root_cgroup_%s=' "$k"
    if [ "$k" = memory.events ] || [ "$k" = cpu.stat ]; then tr '\n' ';' < "$p"; printf '\n'; else cat "$p"; fi
  else
    printf 'observer_root_cgroup_%s=unavailable\n' "$k"
  fi
done
# Inspect the actual Flash listener, never the observer's root cgroup.
# Even a full visible walk can hide ancestors in a delegated cgroup namespace.
# Report visible headroom only; owner-side scope validation is a separate gate.
ram_snapshot=''
if command -v python3 >/dev/null 2>&1 && command -v ss >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
  ram_snapshot=$(timeout -k 1s 8s python3 - <<'PYCGROUP'
import os
import re
import subprocess
from pathlib import Path, PurePosixPath

def read(path):
    return Path(path).read_text().strip()

def listener():
    rows = subprocess.check_output(
        ["ss", "-H", "-ltnp", "sport = :8081"], text=True, timeout=2
    ).splitlines()
    pids = set()
    for row in rows:
        owners = re.findall(r"pid=(\d+),fd=\d+", row)
        if not owners:
            raise ValueError("listener owner unavailable")
        pids.update(owners)
    if len(pids) != 1:
        raise ValueError("ambiguous listener")
    return pids.pop()

def identity(pid):
    proc = Path("/proc") / pid
    # comm can contain spaces and parentheses; fields after the last ')' start at field 3.
    ticks = read(proc / "stat").rsplit(")", 1)[1].split()[19]
    exe = os.path.basename(os.readlink(proc / "exe"))
    if exe != "llama-server" or not ticks.isdecimal():
        raise ValueError("unexpected serving process")
    for ns in ("cgroup", "mnt", "net"):
        if os.readlink(proc / "ns" / ns) != os.readlink("/proc/self/ns/" + ns):
            raise ValueError("namespace mismatch")
    membership = read(proc / "cgroup").splitlines()
    if len(membership) != 1 or not membership[0].startswith("0::/"):
        raise ValueError("not a unified cgroup")
    return ticks, membership[0][3:]

def mount():
    candidates = []
    for line in read("/proc/self/mountinfo").splitlines():
        left, right = line.split(" - ", 1)
        fields = left.split()
        if right.split()[0] == "cgroup2":
            # Do not guess through escaped paths or a subtree-only mount.
            if fields[3] != "/" or "\\" in fields[4]:
                continue
            candidates.append(Path(fields[4]))
    if len(candidates) != 1:
        raise ValueError("ambiguous cgroup2 mount")
    return candidates[0]

def visible_headroom(root, membership):
    rel = PurePosixPath(membership)
    if not rel.is_absolute() or ".." in rel.parts:
        raise ValueError("invalid membership")
    leaf = root.joinpath(*rel.parts[1:])
    if leaf.resolve() != leaf or root.resolve() != root:
        raise ValueError("unexpected symlink")
    current = leaf
    limits = []
    count = 0
    while True:
        count += 1
        if count > 128:
            raise ValueError("ancestor depth")
        maximum = current / "memory.max"
        usage = current / "memory.current"
        # The real cgroup v2 root may expose neither memory controller file.
        if current == root and not maximum.exists() and not usage.exists():
            break
        cap, used = read(maximum), read(usage)
        if not used.isascii() or not used.isdecimal():
            raise ValueError("invalid usage")
        if cap != "max":
            if not cap.isascii() or not cap.isdecimal():
                raise ValueError("invalid limit")
            limits.append(max(0, int(cap) - int(used)))
        if current == root:
            break
        current = current.parent
    return min(limits) if limits else None

try:
    pid = listener()
    before = identity(pid)
    root = mount()
    headroom = visible_headroom(root, before[1])
    if listener() != pid or identity(pid) != before or mount() != root:
        raise ValueError("serving identity changed")
    print("cgroup_serving_pid=" + pid)
    print("cgroup_serving_startticks=" + before[0])
    print("cgroup_visible_headroom_bytes=" + ("unavailable" if headroom is None else str(headroom)))
    # Preserve the old threshold key, but never emit a positive admission
    # from a container-local diagnostic: hidden ancestors remain possible.
    state = "HOLD_LOW_HEADROOM" if headroom is not None and headroom < 2147483648 else "HOLD_SCOPE_UNVERIFIED"
    print("cgroup_mem_headroom_bytes=unavailable")
    print("cgroup_ram_2gib_threshold=" + state)
except (OSError, ValueError, IndexError, RuntimeError, subprocess.SubprocessError):
    print("cgroup_visible_headroom_bytes=unavailable")
    print("cgroup_mem_headroom_bytes=unavailable")
    print("cgroup_ram_2gib_threshold=HOLD_UNKNOWN")
PYCGROUP
  ) || ram_snapshot=''
fi
if [ -n "$ram_snapshot" ]; then
  printf '%s\n' "$ram_snapshot"
else
  echo 'cgroup_visible_headroom_bytes=unavailable'
  echo 'cgroup_mem_headroom_bytes=unavailable'
  echo 'cgroup_ram_2gib_threshold=HOLD_UNKNOWN'
fi
for k in cpu memory io; do
  p="/proc/pressure/$k"
  if [ -r "$p" ]; then printf 'psi_%s=' "$k"; head -n 1 "$p"; else printf 'psi_%s=unavailable\n' "$k"; fi
done
df -P -B1 / 2>/dev/null | awk 'NR==2 {printf "root_bytes_total=%s root_bytes_used=%s root_bytes_available=%s\n", $2, $3, $4}'
if [ -n "$gpu_rows" ]; then
  printf '%s\n' "$gpu_rows" | awk -F, '{printf "gpu_index=%s gpu_used_MiB=%s gpu_free_MiB=%s gpu_total_MiB=%s gpu_util_pct=%s\n", $1, $2, $3, $4, $5}'
else
  echo 'gpu_inventory=unavailable'
fi
