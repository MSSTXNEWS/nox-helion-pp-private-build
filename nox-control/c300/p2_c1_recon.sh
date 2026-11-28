echo "C300: p2_c1_recon.sh"
W=/workspace; N=$W/nox
df -BM $W | tail -1 | awk '{print "free_mb="$4}'
echo "== listing subcores/big (path size)"
find $N/models/subcores $N/models/big -xdev -type f -printf '%s %p\n' | sort -rn | head -30 | awk '{printf "%.2fG %s\n",$1/1073741824,$2}'
echo "== refs (files mentioning), excl venv/models/hf_home/state/backup/logs"
for k in "Qwen3-30B-A3B-Thinking" "OpenCodeReasoning" "models/subcores" "models/big"; do
 echo "ref[$k]:"; timeout 150 grep -rIl --exclude-dir=venv --exclude-dir=venv_tools --exclude-dir=voice2_venv --exclude-dir=models --exclude-dir=hf_home --exclude-dir=backup --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=__pycache__ --exclude-dir=build --exclude-dir=runners --exclude='*.log' --exclude='*.db' --exclude='*.jsonl' -e "$k" $N /etc/systemd/system 2>/dev/null | head -8
done
echo "== procs cmd refs"
for d in /proc/[0-9]*; do tr '\0' ' ' <$d/cmdline 2>/dev/null | grep -E "subcores|models/big" | cut -c1-150; done | head
echo "== open files under subcores/big"
ls -l /proc/[0-9]*/fd 2>/dev/null | grep -E "models/(subcores|big)" | head -3
echo "== open ckpt_keep/pc_jail/ops candidates"
ls -l /proc/[0-9]*/fd 2>/dev/null | grep -oE "$W/[^ ]*(ckpt_keep|pc_jail|v5_live_adapter|v5_ready4850|v5_knowledge_gpu|v5_distill100|nox-backup)[^ ]*" | sort -u | head -20
echo "== sizes"
du -xsm $W/pc_jail/outbox/warm/cand_step_0275* $N/distill_v2/ckpt_keep/best_prevhold_step_0050* $N/distill_v2/ckpt_keep/latest_step_0120* 2>/dev/null
ls -d $W/pc_jail/outbox/warm/cand_step_0275*
echo "== backups"; ls -d $N/backup/* | xargs -n1 du -xsm
echo "== rclone about/ls"
rclone about gdrive: 2>&1 | head -4
rclone lsf gdrive: --max-depth 1 2>&1 | head -20
rclone lsf gdrive:NOX_ARCHIVE --max-depth 2 2>&1 | head -30
echo "== tmp old"; find /tmp -xdev -type f -mtime +2 -printf '%s\n' 2>/dev/null | awk '{s+=$1;n++} END{print "tmp_old_files="n" mb="int(s/1048576)}'
echo END
