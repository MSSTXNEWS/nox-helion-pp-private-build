#!/bin/bash
# SPD-01 recon_s1: что реально есть на S1 для ускорения GLM-5.3. Только чтение (кроме квитанции). Метка #S1.
# Использование: bash recon_s1.sh [--dry-run] [--bin /root/nox/llama.cpp/build/bin/llama-server]
# Квитанция: $RECEIPTS/SPD-01.json (по умолчанию /root/nox/receipts)
BIN=/root/nox/llama.cpp/build/bin/llama-server; DRY=0
while [ $# -gt 0 ]; do case "$1" in --dry-run) DRY=1;; --bin) BIN="$2"; shift;; *) echo "unknown $1" >&2; exit 2;; esac; shift; done
RECEIPTS=${RECEIPTS:-/root/nox/receipts}
if [ $DRY -eq 1 ]; then
  echo "DRY: соберу CPU (модель, avx512/amx, физ.ядра), NUMA, cgroup cpu.max/memory.max, THP+shmem_enabled, HugePages, PCIe gen/width, RAM BW (python bytearray), поддержку флагов в '$BIN --help' (draft-mtp, spec-type, moe-cache-mib, cache-ram, cache-reuse, slot-save-path, n-cpu-moe, numa), свободную VRAM; запишу $RECEIPTS/SPD-01.json"; exit 0
fi
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
LS=$(lscpu 2>/dev/null)
echo "$LS" > $T/lscpu
nvidia-smi --query-gpu=name,memory.total,memory.used,pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max,clocks.sm,driver_version,compute_cap --format=csv,noheader > $T/gpu 2>/dev/null || echo "" > $T/gpu
for f in /sys/fs/cgroup/cpu.max /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpuset.cpus.effective /sys/kernel/mm/transparent_hugepage/enabled /sys/kernel/mm/transparent_hugepage/shmem_enabled /sys/kernel/mm/transparent_hugepage/defrag; do
  printf '%s=%s\n' "$f" "$(cat $f 2>/dev/null | tr '\n' ' ')"; done > $T/sys
grep -E "HugePages_(Total|Free)|Hugepagesize|MemTotal|MemAvailable|Shmem:" /proc/meminfo > $T/mem
df -B1 --output=size,avail /dev/shm 2>/dev/null | tail -1 > $T/shm
lscpu -p=CORE,SOCKET,NODE 2>/dev/null | grep -v '^#' | sort -u > $T/cores
ls /sys/devices/system/node 2>/dev/null | grep -c '^node[0-9]' > $T/nodes
if [ -x "$BIN" ]; then
  H=$("$BIN" --help 2>&1); echo "$H" > $T/help
  strings "$BIN" 2>/dev/null | grep -m1 GGML_OP_OFFLOAD_MIN_BATCH > $T/opoff
  (cd "$(dirname "$BIN")/../.." 2>/dev/null && git log -1 --format='%h %cd' --date=short 2>/dev/null) > $T/gitrev
else : > $T/help; : > $T/opoff; : > $T/gitrev; fi
pgrep -af llama-server | cut -c1-300 > $T/procs
python3 - "$T" "$BIN" "$RECEIPTS" <<'PY'
import json, os, re, sys, time
T, BIN, RC = sys.argv[1:4]
rd = lambda n: open(os.path.join(T, n), errors="replace").read()
ls = rd("lscpu"); kv = {}
for l in ls.splitlines():
    if ":" in l:
        k, v = l.split(":", 1); kv[k.strip()] = v.strip()
cores = [l.split(",") for l in rd("cores").splitlines() if l.strip()]
phys = len(cores)
flags = kv.get("Flags", "")
sysd = dict(l.split("=", 1) for l in rd("sys").splitlines() if "=" in l)
cpu_max = sysd.get("/sys/fs/cgroup/cpu.max", "").strip()
quota = None
m = re.match(r"(\d+)\s+(\d+)", cpu_max)
if m: quota = round(int(m.group(1)) / int(m.group(2)), 2)
# RAM bandwidth: копирование 512 МиБ буфера (одно ядро, нижняя оценка; многопоточный потолок выше)
buf = bytearray(512 * 2**20); best = 0.0
for _ in range(3):
    t = time.time(); b2 = bytes(buf); dt = time.time() - t
    best = max(best, 2 * len(buf) / dt / 1e9)  # чтение+запись
del buf, b2
help_t = rd("help")
def has(s): return s in help_t
gpu = rd("gpu").strip().split(", ") if rd("gpu").strip() else []
mem = dict(re.findall(r"(\w+):\s+(\d+)", rd("mem")))
thp_shm = sysd.get("/sys/kernel/mm/transparent_hugepage/shmem_enabled", "")
hints = []
nodes = int((rd("nodes").strip() or "1"))
if nodes > 1: hints.append("NUMA узлов=%d: тестировать --numa distribute / numactl --interleave=all (рычаг L10)" % nodes)
else: hints.append("NUMA узел один: --numa не даёт эффекта, пропустить L10")
if quota and quota < int(kv.get("CPU(s)", "0") or 0): hints.append("cgroup квота %.1f vCPU < видимых %s: -t/-tb не больше квоты, иначе троттлинг" % (quota, kv.get("CPU(s)")))
hints.append("физ.ядер (уникальных CORE) = %d: рычаг L01 -t ~ физ.ядра в пределах квоты" % phys)
if "[never]" in thp_shm or "never" in thp_shm.split("[")[0:1]: hints.append("shmem THP выключен; модель из /dev/shm без hugepages (менять нельзя без root S1; A/B)")
if has("draft-mtp"): hints.append("draft-mtp ЕСТЬ в --help: тестировать L05/L06")
else: hints.append("draft-mtp НЕТ в --help: нужна сборка не старше PR #29928 (GLM5Next MTP, b11474+); см. SPD-07")
out = {"id": "SPD-01", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "host": os.uname().nodename,
       "cpu": {"model": kv.get("Model name"), "vcpu": kv.get("CPU(s)"), "sockets": kv.get("Socket(s)"),
               "threads_per_core": kv.get("Thread(s) per core"), "physical_cores_visible": phys, "numa_nodes": nodes,
               "avx2": " avx2" in " " + flags, "avx512f": "avx512f" in flags, "avx512_vnni": "avx512_vnni" in flags,
               "avx512_bf16": "avx512_bf16" in flags, "amx_tile": "amx_tile" in flags, "amx_int8": "amx_int8" in flags},
       "cgroup": {"cpu_max": cpu_max, "vcpu_quota": quota, "memory_max": sysd.get("/sys/fs/cgroup/memory.max", "").strip(),
                  "cpuset": sysd.get("/sys/fs/cgroup/cpuset.cpus.effective", "").strip()},
       "thp": {"enabled": sysd.get("/sys/kernel/mm/transparent_hugepage/enabled", "").strip(), "shmem_enabled": thp_shm.strip(),
               "defrag": sysd.get("/sys/kernel/mm/transparent_hugepage/defrag", "").strip(),
               "hugepages_total": int(mem.get("HugePages_Total", 0)), "hugepagesize_kb": int(mem.get("Hugepagesize", 0))},
       "ram": {"mem_total_kb": int(mem.get("MemTotal", 0)), "mem_avail_kb": int(mem.get("MemAvailable", 0)),
               "copy_bw_gbs_1thread": round(best, 1), "dev_shm_size_avail_bytes": rd("shm").split()},
       "gpu": dict(zip(["name", "mem_total", "mem_used", "pcie_gen", "pcie_gen_max", "pcie_width", "pcie_width_max", "sm_clock", "driver", "cc"], gpu)),
       "llama": {"bin": BIN, "present": os.access(BIN, os.X_OK), "git": rd("gitrev").strip(),
                 "draft_mtp": has("draft-mtp"), "spec_type": has("--spec-type"), "moe_cache_mib": has("--moe-cache-mib"),
                 "cache_ram": has("--cache-ram"), "cache_reuse": has("--cache-reuse"), "slot_save_path": has("--slot-save-path"),
                 "n_cpu_moe": has("--n-cpu-moe"), "numa": has("--numa"), "no_op_offload": has("--no-op-offload"),
                 "op_offload_min_batch_env": bool(rd("opoff").strip())},
       "llama_server_procs": rd("procs").splitlines(), "hints": hints}
os.makedirs(RC, exist_ok=True)
json.dump(out, open(os.path.join(RC, "SPD-01.json"), "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: out[k] for k in ("cpu", "cgroup", "thp", "gpu", "llama", "hints")}, ensure_ascii=False, indent=1))
PY
