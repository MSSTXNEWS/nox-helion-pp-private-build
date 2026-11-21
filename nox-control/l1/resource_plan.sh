#!/bin/bash
# L1 resource_plan: default = READ-ONLY dry-run that prints a recommended resource split.
#   --apply     apply ONLY safe tweaks (trainer nice/ionice/oom_score_adj, vm.swappiness=10) with backup
#   --rollback  restore from the latest backup
# Never drops caches, never restarts services, never touches the chat model process.
set -u
MODE=plan; [ "${1:-}" = "--apply" ] && MODE=apply; [ "${1:-}" = "--rollback" ] && MODE=rollback
TRAINER_PATTERN="${TRAINER_PATTERN:-train_qwen35|run_train_t131u|nox-train}"
CHAT_PATTERN="${CHAT_PATTERN:-llama-server|ds41}"
BACKUP_ROOT="${L1_BACKUP_DIR:-/root/nox/state/l1_backup}"
MIN_FREE_MIB="${MIN_FREE_MIB:-12000}"
log(){ echo "$@"; }

trainer_pids(){ pgrep -f "$TRAINER_PATTERN" 2>/dev/null | grep -vx "$$" | grep -vx "$PPID" || true; }

if [ "$MODE" = rollback ]; then
  d=$(ls -1d "$BACKUP_ROOT"/* 2>/dev/null | sort | tail -1); [ -n "$d" ] || { log "no backup in $BACKUP_ROOT"; exit 1; }
  log "rollback from $d"
  [ -f "$d/swappiness" ] && sysctl -w vm.swappiness="$(cat "$d/swappiness")" >/dev/null 2>&1 && log "swappiness restored"
  while read -r pid nice oom; do
    [ -d "/proc/$pid" ] || continue
    renice -n "$nice" -p "$pid" >/dev/null 2>&1; echo "$oom" > "/proc/$pid/oom_score_adj" 2>/dev/null
    log "pid $pid restored nice=$nice oom=$oom"
  done < "$d/pids.txt"
  exit 0
fi

log "== GPU (VRAM MiB)"
BEST=""; BESTFREE=-1
if command -v nvidia-smi >/dev/null 2>&1; then
  while IFS=, read -r i name tot free; do
    i=${i// /}; free=${free// /}; tot=${tot// /}
    log "GPU$i $name total=${tot} free=${free}"
    [ "${free:-0}" -gt "$BESTFREE" ] && { BESTFREE=$free; BEST=$i; }
  done < <(nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader,nounits 2>/dev/null)
else log "nvidia-smi not found"; fi
log "== RAM"; free -m 2>/dev/null | head -3
SW=$(sysctl -n vm.swappiness 2>/dev/null || echo ?); log "vm.swappiness=$SW"
log "== disk"; df -h / 2>/dev/null | tail -1
USE=$(df / 2>/dev/null | awk 'NR==2{gsub("%","",$5);print $5}')
log "== supervisor"; { supervisorctl status 2>/dev/null || log "supervisorctl unavailable"; } | head -40
log "== processes"
CHAT=$(pgrep -f "$CHAT_PATTERN" 2>/dev/null | head -3 | tr '\n' ' '); TR=$(trainer_pids | tr '\n' ' ')
log "chat pids: ${CHAT:-none}   trainer pids: ${TR:-none}"

NCPU=$(nproc 2>/dev/null || echo 8)
MEMTOT=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)
log ""; log "== RECOMMENDED (dry-run)"
log "1. Priority: chat (DeepSeek) first, trainer yields."
[ -n "$BEST" ] && log "2. Trainer GPU: GPU$BEST (free ${BESTFREE} MiB); start only if free >= MIN_FREE_MIB=$MIN_FREE_MIB" || log "2. Trainer GPU: unknown"
[ "$BESTFREE" -ge 0 ] && [ "$BESTFREE" -lt "$MIN_FREE_MIB" ] && log "   WARNING: free VRAM below MIN_FREE_MIB, do not start trainer"
log "3. MIN_FREE_MIB=$MIN_FREE_MIB (keep >=2000 MiB headroom for chat KV cache)"
log "4. THREADS: chat -t $((NCPU*5/8)) / -tb $((NCPU*5/4)) leave ~$((NCPU*3/8)) cores for trainer/dataloader (bench via c78 before changing)"
log "5. MOE_CACHE_MIB: ~$((MEMTOT/10)) (≈10% of ${MEMTOT} MiB RAM); rest stays page cache for mmap'd experts"
log "6. oom_score_adj: trainer +500 (killed first), chat -500"
log "7. trainer: nice 10, ionice -c2 -n7"
log "8. cgroup: trainer memory.high=$((MEMTOT*45/100))M (manual; e.g. systemd-run -p MemoryHigh=... or /sys/fs/cgroup/<grp>/memory.high)"
log "9. vm.swappiness=10 (now $SW); do NOT drop caches"
[ "${USE:-0}" -ge 90 ] && log "10. Disk ${USE}% full: run disk_report.sh, free space before new checkpoints"
[ "$MODE" = plan ] && { log ""; log "dry-run only; use --apply for safe tweaks, --rollback to undo"; exit 0; }

# ---- apply (safe subset) ----
[ "$(id -u)" -eq 0 ] || { log "--apply needs root"; exit 1; }
d="$BACKUP_ROOT/$(date +%Y%m%dT%H%M%S)"; mkdir -p "$d" || exit 1
echo "$SW" > "$d/swappiness"; : > "$d/pids.txt"
for pid in $(trainer_pids); do
  [ -d "/proc/$pid" ] || continue
  n=$(ps -o ni= -p "$pid" | tr -d ' '); o=$(cat "/proc/$pid/oom_score_adj" 2>/dev/null || echo 0)
  echo "$pid ${n:-0} $o" >> "$d/pids.txt"
  renice -n 10 -p "$pid" >/dev/null 2>&1; ionice -c2 -n7 -p "$pid" >/dev/null 2>&1
  echo 500 > "/proc/$pid/oom_score_adj" 2>/dev/null; log "applied to trainer pid $pid"
done
sysctl -w vm.swappiness=10 >/dev/null 2>&1 && log "vm.swappiness=10"
log "backup: $d (rollback: $0 --rollback)"
