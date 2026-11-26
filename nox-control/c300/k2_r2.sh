echo "C300: k2_r2"
N=/workspace/nox
echo "--- owner"; ls -la --time-style=full-iso $N/state | grep -i owner; find $N/state -maxdepth 2 -iname "*OWNER_ACTIVE*" -exec ls -la --time-style=full-iso {} \; 2>/dev/null | head
echo "--- who launches 8104"; grep -rIl -- "--port 8104\|8104" $N/ops $N/agent/*.sh $N/stewards /etc/supervisor/conf.d 2>/dev/null | head -20
echo "--- body_ttft_upgrade"; sed -n 1,80p $N/ops/body_ttft_upgrade.sh | cut -c1-260
echo "--- parent of 8104 / 8105"; ps -o pid,ppid,args -p 3626380 | cut -c1-200
echo "--- 8090/8301 procs"; ps -eo pid,ppid,etimes,args | grep -E "python" | grep -E "8090|8301|8091" | grep -v grep | cut -c1-300
ls /etc/supervisor/conf.d/ >/dev/null; grep -l "8090\|8301" /etc/supervisor/conf.d/* 2>/dev/null
grep -rIn "8090\|8301" $N/ops/*.sh $N/agent/*.sh $N/web/pkg/server/run_web.sh $N/stewards/*.sh 2>/dev/null | cut -c1-220 | head -30
echo "--- nox_runners.conf"; head -12 /etc/supervisor/conf.d/nox_runners.conf
echo "--- meili"; ls /workspace/nox/logs 2>/dev/null | grep -i meili; find $N -maxdepth 3 -iname "*meili*" -not -path "*/venv/*" 2>/dev/null | head; ps -eo pid,ppid,etimes,args | grep -i meili | grep -v grep | cut -c1-250
echo "--- tunnels"; ps -eo pid,ppid,etimes,args | grep -E "ssh .*-[LR]|gb10|tunnel" | grep -v grep | cut -c1-260
echo "--- thinking file"; ls -la $N/models/subcores/*/ 2>&1 | cut -c1-200
ps -eo pid,etimes,args | grep -E "wget|curl|aria|hf_|huggingface|download" | grep -v grep | cut -c1-250
echo "--- 8143 rss"; ps -eo pid,rss,args | sort -k2 -nr | head -12 | cut -c1-200
