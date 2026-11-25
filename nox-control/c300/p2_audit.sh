#!/bin/bash
# P2 read-only audit. No writes except stdout.
echo "## HOST"; date -u; uptime; nproc; free -m
echo "## DF"; df -h 2>/dev/null | grep -vE 'tmpfs|overlay$' | head -20; df -h / /tmp /workspace 2>/dev/null
echo "## NVIDIA"; nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu --format=csv 2>&1
nvidia-smi --query-compute-apps=pid,used_memory,name --format=csv 2>&1
echo "## PS_CPU"; ps -eo pid,ppid,stat,etimes,pcpu,pmem,rss,user,args --sort=-pcpu 2>/dev/null | cut -c1-230 | head -40
echo "## PS_RAM"; ps -eo pid,ppid,stat,etimes,pcpu,pmem,rss,args --sort=-rss 2>/dev/null | cut -c1-230 | head -25
echo "## PS_OLDEST"; ps -eo pid,ppid,stat,etimes,pcpu,rss,args --sort=-etimes 2>/dev/null | cut -c1-200 | head -40
echo "## ZOMBIES"; ps -eo pid,ppid,stat,args | awk '$3 ~ /^Z/' | head -30
echo "## PY_NODE"; ps -eo pid,ppid,stat,etimes,time,pcpu,rss,args | grep -E 'python|node' | grep -v grep | cut -c1-260
echo "## DUP_SCRIPTS"; ps -eo args | grep -E 'python|node|bash .*\.sh' | grep -v grep | sed 's/^ *//' | sort | uniq -c | awk '$1>1' | cut -c1-240
echo "## OLD_IDLE (>1d, cpu<1%)"; ps -eo pid,etimes,pcpu,rss,args | awk 'NR>1 && $2>86400 && $3<1.0' | cut -c1-220 | head -40
echo "## KEYPROCS"; ps -eo pid,etimes,pcpu,rss,args | grep -Ei 'train|r2_queue|disk_janitor|worm|worms|nexus|c07|arbit|llama|web_server|brain' | grep -v grep | cut -c1-240
echo "## SYSTEMD"; (systemctl list-units --type=service --state=running --no-pager 2>&1 | head -40) ; systemctl --failed --no-pager 2>&1 | head -10
echo "## SCREEN_TMUX"; screen -ls 2>&1 | head -20; tmux ls 2>&1 | head -20
echo "## SUPERVISOR"; (supervisorctl status 2>&1 | head -40)
echo "## CRON"; crontab -l 2>&1 | head -30; ls /etc/cron.d 2>&1 | head
echo "## PORTS"; ss -ltnpH 2>/dev/null | awk '{print $4, $6}' | cut -c1-150 | sort -u | head -60
for p in 8091 8200 8104 8300 8400 8130 18215 18216 8793 4210 4000 4220 4100; do
  l=$(ss -ltnpH "sport = :$p" 2>/dev/null | awk '{print $6}' | head -1); echo "port $p: ${l:-NOT_LISTENING}"; done
echo "## DISK_TOP"; du -xsh /root/.cache /root/.cache/* /root/.npm /tmp /var/tmp /var/log /workspace /root 2>/dev/null | sort -rh | head -30
du -xh --max-depth=1 /workspace 2>/dev/null | sort -rh | head -25
echo "## BACKUPS"; find / -xdev \( -iname '*backup*' -o -iname '*.bak' -o -iname '*.bak.*' \) -maxdepth 5 2>/dev/null | head -40
echo "## TMP_OLD3H"; find /tmp -xdev -mmin +180 2>/dev/null | wc -l; du -sh /tmp 2>/dev/null
echo "## LARGEST_FILES"; find / -xdev -type f -size +500M -printf '%s %TY-%Tm-%Td %p\n' 2>/dev/null | sort -rn | head -25 | awk '{printf "%.1fG %s %s\n",$1/1073741824,$2,$3}'
echo "## DONE"
