N=/workspace/nox; A=$N/agent/autotrain
echo "S4P10 $(date +%F_%H:%M) mode=$(cat $A/mode 2>/dev/null)"
for f in $A/donor_*.cmd*; do echo "## $(basename $f) $(stat -c %s $f)B"; tr '\n' ' ' < $f | grep -o -E -- "--(n-cpu-moe|parallel|ctx-size|cache-type-[kv]|mmproj|n-gpu-layers|batch-size|ubatch-size|cache-reuse|no-mmproj)[ =][^ ]*|-(c|ngl|np|b|ub|ctk|ctv|fa) [^ ]*" | tr '\n' ' '; echo; done 2>/dev/null | cut -c1-400
echo "## known_good->"; ls -la $A/donor_*known_good 2>/dev/null | awk '{print $5,$9}'
echo "## util tail"; tail -n 2 $N/state/orch/util.jsonl | cut -c1-400
echo "## vram history files"; ls $N/state/*vram* $N/state/orch/*vram* $N/state/p5* $N/ops/p5* 2>/dev/null | head
echo "## nox_gpu_total"; nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits
echo "## last restarts"; tail -n 12 $N/state/body_restart.log 2>/dev/null | cut -c1-260
echo "## backup scripts"; ls $N/canon/ 2>/dev/null | head -30; ls $N/canon/soul 2>/dev/null | tail -8; grep -rIl --include=*.sh --include=*.py "soul_h" $N/ops $N/mods $N/canon $N/agent 2>/dev/null | head -5
echo "## supervisor conf"; ls /etc/supervisor/conf.d 2>/dev/null | head -50 | tr '\n' ' '
