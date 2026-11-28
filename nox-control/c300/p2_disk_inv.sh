echo "C300: p2_disk_inv.sh"
# READ-ONLY inventory. Nothing is deleted/moved/changed.
IO="ionice -c3 nice -n19"
W=/workspace
df -BG $W | tail -1 | awk '{print "df total="$2" used="$3" free="$4" use="$5}'
U=/tmp/p2_inuse.$$; : > $U
for d in /proc/[0-9]*; do
  ls -l $d/fd 2>/dev/null | grep -oE "$W/[^ ]+" | sed 's/ (deleted)//' >> $U
  c=$(tr '\0' '\n' < $d/cmdline 2>/dev/null | grep -E "^$W/|=$W/" | sed -E "s/^[^=]*=//"); [ -n "$c" ] && echo "$c" >> $U
done
for d in /proc/[0-9]*; do n=$(tr '\0' ' ' < $d/cmdline 2>/dev/null); case "$n" in *llama-server*|*body*) echo "$n" | grep -oE "$W/[^ ]+" >> $U;; esac; done
sort -u $U -o $U; echo "inuse_paths=$(wc -l < $U)"
inuse(){ p="$1"; if [ -d "$p" ]; then grep -q "^$p/" $U && echo USED || echo -; else grep -qxF "$p" $U && echo USED || echo -; fi; }
typ(){ case "$1" in *ckpt*|*checkpoint*|*step_*) echo ckpt;; *adapter*|*lora*) echo adapter;; *.gguf|*.safetensors|*.bin|*models*) echo model;; *.log|*/logs*) echo log;; *cache*|*__pycache__*) echo cache;; *.tar*|*.zip|*.gz|*.zst|*backup*) echo archive;; *) echo other;; esac; }
echo "== TOP dirs (depth<=3) GB mtime type used"
$IO du -xk --max-depth=3 $W 2>/dev/null | sort -rn | head -40 | while read k p; do printf "D %.2f %s %s %s %s\n" $(echo "$k/1048576"|bc -l) "$(date -r "$p" +%F 2>/dev/null)" "$(typ "$p")" "$(inuse "$p")" "$p"; done
echo "== TOP files >=100MB"
$IO find $W -xdev -type f -size +100M -printf '%s\t%TY-%Tm-%Td\t%p\n' 2>/dev/null | sort -rn | head -40 > /tmp/p2_files.$$
while IFS=$'\t' read s m p; do printf "F %.2f %s %s %s %s\n" $(echo "$s/1073741824"|bc -l) "$m" "$(typ "$p")" "$(inuse "$p")" "$p"; done < /tmp/p2_files.$$
echo "== dup by size (files>=100MB, sha256 on same-size groups, max 12 groups)"
$IO find $W -xdev -type f -size +100M -printf '%s %p\n' 2>/dev/null | sort -n | awk '{c[$1]++; l[$1]=l[$1]" "$2} END{for(s in c) if(c[s]>1) print s, l[s]}' | sort -rn | head -12 | while read s rest; do echo "grp size_gb=$(echo "$s/1073741824"|bc -l|cut -c1-5)"; for f in $rest; do echo "  $($IO sha256sum "$f" | cut -c1-12) $f"; done; done
echo "== (a) recoverable GB"
gb(){ k=$($IO du -xskL "$@" 2>/dev/null | awk '{s+=$1} END{print s+0}'); printf "%.2f" $(echo "$k/1048576"|bc -l); }
for p in /root/.cache/pip /root/.cache/huggingface /root/.cache/torch /root/.cache/uv /root/.cache /home/*/.cache /tmp /var/tmp /var/cache/apt /var/log $W/.cache $W/tmp; do [ -e "$p" ] && echo "A $(gb $p) $p"; done
echo "A pycache_total $(find $W -xdev -type d -name __pycache__ -prune -print0 2>/dev/null | xargs -0 du -xsk 2>/dev/null | awk '{s+=$1} END{printf "%.2f", s/1048576}') (dirs=$(find $W -xdev -type d -name __pycache__ 2>/dev/null | wc -l))"
echo "A logs_older7d_in_workspace $(find $W -xdev -type f \( -name '*.log' -o -name '*.log.*' -o -name '*.out' \) -mtime +7 -printf '%s\n' 2>/dev/null | awk '{s+=$1} END{printf "%.2f", s/1073741824}')"
echo "A logs_all_in_workspace $(find $W -xdev -type f \( -name '*.log' -o -name '*.log.*' -o -name '*.out' \) -printf '%s\n' 2>/dev/null | awk '{s+=$1} END{printf "%.2f", s/1073741824}')"
echo "A tmp_files_workspace $(find $W -xdev -type f \( -name '*.tmp' -o -name '*.part' -o -name '*.partial' -o -name '*~' \) -printf '%s\n' 2>/dev/null | awk '{s+=$1} END{printf "%.2f", s/1073741824}')"
echo "A top_logs:"; find $W -xdev -type f \( -name '*.log' -o -name '*.log.*' -o -name '*.out' \) -printf '%s %TY-%Tm-%Td %p\n' 2>/dev/null | sort -rn | head -10 | awk '{printf "  %.2fG %s %s\n",$1/1073741824,$2,$3}'
echo "== (b) candidates"
N=$W/nox
for p in $N/distill_v2/ckpt_keep $N/ops/v5_live_adapter_* $N/ops/v5_ready4850_* $N/pc_jail/outbox/warm/cand_step_0275 $N/distill_v2/ckpt $N/distill_v2/ckpt_archive $N/backup; do [ -e "$p" ] && printf "B %s %s %s %s\n" "$(gb $p)" "$(date -r "$p" +%F)" "$(inuse "$p")" "$p"; done
echo "B_listing distill_v2/ckpt_keep:"; ls -la --time-style=+%F $N/distill_v2/ckpt_keep 2>/dev/null | awk '{print "  "$5" "$6" "$7}' | head -20
echo "B_models (gguf/safetensors, GB, mtime, used):"
find $W -xdev -type f \( -name '*.gguf' -o -name '*.safetensors' \) -size +500M -printf '%s\t%TY-%Tm-%Td\t%p\n' 2>/dev/null | sort -rn | head -40 | while IFS=$'\t' read s m p; do printf "  %.2f %s %s %s\n" $(echo "$s/1073741824"|bc -l) "$m" "$(inuse "$p")" "$p"; done
echo "== rclone"
if command -v rclone >/dev/null; then echo "rclone=yes"; rclone listremotes --long 2>/dev/null | sed 's/^/remote: /'; else echo "rclone=no"; fi
for c in /root/.config/rclone/rclone.conf $N/.config/rclone/rclone.conf; do [ -f $c ] && echo "rclone_conf_present=$c"; done
df -BG $W | tail -1 | awk '{print "df_end free="$4}'
rm -f $U /tmp/p2_files.$$
echo END
