echo "K1: p2_clean"
# Создатель 28.11 ~20:45 МСК, явно в форме вопроса: «Да, удаляй (а)» и «Да, удаляй без копии» по списку (б) ниже.
# best_step_0075, cand_dpo_*, свежий бэкап, models/*, warm, student, рисование, ACE-Step — НЕ трогаются.
set -u
W=/workspace; N=$W/nox; M=$N/state/core/deleted_manifest_20261128.jsonl; mkdir -p $N/state/core
free(){ df -BM $W | awk 'NR==2{print $4}'; }
echo "free_before=$(free)"
rec(){ # path kind
  local p="$1" k="$2" sz sh
  sz=$(du -sb "$p" 2>/dev/null | cut -f1)
  if [ -f "$p" ]; then sh=$(sha256sum "$p" | cut -c1-64); else sh=$(find "$p" -type f -print0 2>/dev/null | sort -z | xargs -0 sha256sum 2>/dev/null | sha256sum | cut -c1-64); fi
  printf '{"ts":"%s","path":"%s","bytes":%s,"sha256":"%s","kind":"%s","copy":"none (owner 28.11: delete without copy)"}\n' "$(date -u +%FT%TZ)" "$p" "${sz:-0}" "$sh" "$k" >> $M
}
inuse(){ lsof +D "$1" >/dev/null 2>&1; }
# ---- (а)
n=$(find $W -xdev -type d -name __pycache__ 2>/dev/null | wc -l); find $W -xdev -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null; echo "a_pycache_dirs=$n"
for c in pip huggingface torch; do [ -d /root/.cache/$c ] && { rec /root/.cache/$c cache; rm -rf /root/.cache/$c; echo "a_cache_$c=1"; }; done
t=0; while IFS= read -r -d '' f; do lsof "$f" >/dev/null 2>&1 && continue; rm -f "$f" && t=$((t+1)); done < <(find /tmp -xdev -type f -mtime +2 -print0 2>/dev/null); echo "a_tmp_files=$t"
# ---- (б)
for p in $N/ops/v5_live_adapter_20261125 $N/ops/v5_ready4850_20261124 $W/pc_jail/outbox/warm/cand_step_0275 \
         $N/distill_v2/ckpt_keep/best_prevhold_step_0050 $N/distill_v2/ckpt_keep/latest_step_0120 \
         $N/ops/v5_knowledge_gpu_20261125 $N/ops/v5_distill100_20261125; do
  [ -e "$p" ] || { p2=$(ls -d $W/*/${p##*/} $W/${p#$N/} 2>/dev/null | head -1); [ -n "$p2" ] && p=$p2 || { echo "b_missing ${p##*/}"; continue; }; }
  case "$p" in *best_step_0075*|*cand_dpo_*) echo "b_skip_protected ${p##*/}"; continue;; esac
  if inuse "$p"; then echo "b_inuse_skip ${p##*/}"; continue; fi
  rec "$p" old; rm -rf "$p" && echo "b_deleted ${p##*/}"
done
for d in 20261126 20261127; do
  for p in $(ls -d $W/backup/*$d* $N/backup/*$d* $W/*backup*/*$d* 2>/dev/null | sort -u); do
    case "$p" in *20261128*) continue;; esac
    inuse "$p" && { echo "b_inuse_skip ${p##*/}"; continue; }
    rec "$p" old_backup; rm -rf "$p" && echo "b_deleted ${p##*/}"
  done
done
echo "manifest_rows=$(wc -l < $M)"
echo "free_after=$(free)"
echo END
