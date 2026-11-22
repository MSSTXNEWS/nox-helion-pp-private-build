#!/usr/bin/env bash
# S1  OPT-06 numa_tune.sh - разведка NUMA/cgroup/THP/governor/PCIe и безопасная настройка под llama-server.
# По умолчанию ТОЛЬКО чтение (= --dry-run). Запись только с --apply и только в то, что доступно на запись;
# нет прав = пропуск без повторов (правило владельца). Запреты: --no-mmap/--mlock/drop_caches не трогаем.
# Квитанция: $RECEIPTS/OPT-06.json. Для тестов: --root DIR подменяет /sys и /proc (DIR/sys, DIR/proc).
set -u
ROOT=""; APPLY=0; RECEIPTS="/root/nox/receipts"; DRY=1
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1; APPLY=0 ;;
    --apply) APPLY=1; DRY=0 ;;
    --root) ROOT="$2"; shift ;;
    --receipts-dir) RECEIPTS="$2"; shift ;;
    -h|--help) echo "usage: $0 [--dry-run|--apply] [--root DIR] [--receipts-dir DIR]"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac; shift
done
SYS="$ROOT/sys"; PROC="$ROOT/proc"
rd() { [ -r "$1" ] && head -c 200 "$1" | tr -d '\n' || printf ''; }
count_cpulist() { # "0-3,8,10-11" -> 7
  local n=0 part a b; local IFS=','
  for part in $1; do
    case "$part" in *-*) a=${part%-*}; b=${part#*-}; n=$((n + b - a + 1)) ;; ''|*[!0-9]*) ;; *) n=$((n + 1)) ;; esac
  done; echo "$n"
}
NODES=$(ls -d "$SYS"/devices/system/node/node[0-9]* 2>/dev/null | wc -l)
CPUSET=$(rd "$SYS/fs/cgroup/cpuset.cpus.effective"); [ -z "$CPUSET" ] && CPUSET=$(rd "$SYS/fs/cgroup/cpuset/cpuset.cpus")
MEMS=$(rd "$SYS/fs/cgroup/cpuset.mems.effective")
CPUMAX=$(rd "$SYS/fs/cgroup/cpu.max")
MEMMAX=$(rd "$SYS/fs/cgroup/memory.max")
QUOTA=0; PERIOD=100000
if [ -n "$CPUMAX" ]; then q=${CPUMAX%% *}; p=${CPUMAX##* }; case "$q" in max|'') ;; *) QUOTA=$q; PERIOD=$p ;; esac; fi
VCPU_QUOTA=0; [ "$QUOTA" -gt 0 ] 2>/dev/null && VCPU_QUOTA=$(( (QUOTA + PERIOD - 1) / PERIOD ))
VCPU_SET=0; [ -n "$CPUSET" ] && VCPU_SET=$(count_cpulist "$CPUSET")
VCPU=$VCPU_SET; [ "$VCPU" -eq 0 ] && VCPU=$(nproc 2>/dev/null || echo 1)
if [ "$VCPU_QUOTA" -gt 0 ] && [ "$VCPU_QUOTA" -lt "$VCPU" ]; then VCPU=$VCPU_QUOTA; fi
THREADS_T=$VCPU; [ "$VCPU" -gt 4 ] && THREADS_T=$((VCPU - 2))   # -t: оставить 2 vCPU сервисам (A12); мерить колено OPT-05
THP=$(rd "$SYS/kernel/mm/transparent_hugepage/enabled"); THP_SHMEM=$(rd "$SYS/kernel/mm/transparent_hugepage/shmem_enabled")
NB=$(rd "$PROC/sys/kernel/numa_balancing"); GOV=$(rd "$SYS/devices/system/cpu/cpu0/cpufreq/scaling_governor")
SMT=$(rd "$SYS/devices/system/cpu/smt/active")
NUMACTL=0; command -v numactl >/dev/null 2>&1 && NUMACTL=1
PCIE=""; if command -v nvidia-smi >/dev/null 2>&1 && [ -z "$ROOT" ]; then
  PCIE=$(nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current --format=csv,noheader 2>/dev/null | head -1 | tr -d ' '); fi
# Рекомендации (гипотезы, мерить A/B в SPD-02): интерливинг имеет смысл только при >1 узла NUMA.
REC_PREFIX=""; REC_NUMA_FLAG=""
if [ "$NODES" -gt 1 ]; then
  [ "$NUMACTL" = 1 ] && REC_PREFIX="numactl --interleave=all"; REC_NUMA_FLAG="--numa distribute"
fi
NOTES=""; add_note() { NOTES="${NOTES:+$NOTES; }$1"; }
[ "$NODES" -le 1 ] && add_note "1 узел NUMA: interleave/--numa не нужны"
[ "${NB:-0}" = "1" ] && add_note "numa_balancing=1: выключить (--apply) если разрешено"
case "$GOV" in performance|'') ;; *) add_note "governor=$GOV, нужен performance" ;; esac
case "$THP_SHMEM" in *"[never]"*) add_note "THP shmem=never: memfd/tmpfs без hugepages (менять нужен root хоста)" ;; esac
[ "$SMT" = "1" ] && add_note "SMT активен: vCPU могут быть гипертредами, -t мерить по колену (OPT-05)"
APPLIED=""
try_write() { # file value label
  if [ -w "$1" ]; then
    if printf '%s' "$2" > "$1" 2>/dev/null; then APPLIED="${APPLIED:+$APPLIED,}\"$3\""; else add_note "не удалось записать $3"; fi
  else add_note "нет прав на запись $3 (пропуск)"; fi
}
if [ "$APPLY" = 1 ]; then
  [ "${NB:-0}" = "1" ] && try_write "$PROC/sys/kernel/numa_balancing" 0 numa_balancing
  case "$GOV" in performance|'') ;; *) try_write "$SYS/devices/system/cpu/cpu0/cpufreq/scaling_governor" performance governor_cpu0 ;; esac
fi
js() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
mkdir -p "$RECEIPTS" 2>/dev/null
OUT="$RECEIPTS/OPT-06.json"
cat > "$OUT" <<JSON
{"id":"OPT-06","ts":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","mode":"$([ "$APPLY" = 1 ] && echo apply || echo dry-run)",
 "numa_nodes":$NODES,"cpuset":"$(js "$CPUSET")","mems":"$(js "$MEMS")","vcpu_effective":$VCPU,"vcpu_quota":$VCPU_QUOTA,
 "memory_max":"$(js "$MEMMAX")","thp_enabled":"$(js "$THP")","thp_shmem":"$(js "$THP_SHMEM")","numa_balancing":"$(js "$NB")",
 "governor":"$(js "$GOV")","smt_active":"$(js "$SMT")","numactl_present":$NUMACTL,"pcie_gen_cur_max_width":"$(js "$PCIE")",
 "recommend":{"threads_t":$THREADS_T,"threads_tb":$VCPU,"prefix":"$(js "$REC_PREFIX")","numa_flag":"$(js "$REC_NUMA_FLAG")"},
 "applied":[${APPLIED}],"notes":"$(js "$NOTES")"}
JSON
if [ -f "$OUT" ]; then echo "receipt: $OUT"; cat "$OUT"; else echo "receipt write failed: $OUT" >&2; exit 3; fi
exit 0
