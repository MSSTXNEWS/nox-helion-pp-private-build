#!/bin/bash
# Загрузка блока 1 (D01-01..20) на сервер и запуск по режиму из MODE: dry | check | run | status
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/block1
mkdir -p /root/nox/scripts /root/nox/logs /root/nox/receipts
curl -fsSL "$R/NOX_BLOCK1.tgz" -o /tmp/b1.tgz && tar xzf /tmp/b1.tgz -C /root/nox/ || { echo "download/extract failed"; exit 1; }
MODE="$(curl -fsSL "$R/MODE?t=$RANDOM" | tr -d '[:space:]')"
chmod +x /root/nox/scripts/*.sh /root/nox/scripts/lib/*.sh 2>/dev/null
[ -f /root/nox/nox.env ] || printf 'NOX_SERVER=S1\nNOX_S1_SSH="-p 62281 root@174.88.252.223"\n' > /root/nox/nox.env
SRV=S1; nvidia-smi -L 2>/dev/null | grep -q V100 && SRV=S2
cd /root/nox/scripts; [ "$SRV" = S2 ] && export NOX_ONLY="P1-T07 P1-19 P1-T10 P1-T05 P10-13"; export NOX_SKIP="${NOX_SKIP:-P1-15}"
echo "MODE=$MODE SRV=$SRV host=$(hostname)"
case "$MODE" in
  run_dry) NOX_SERVER=$SRV timeout 250 ./run_block1.sh --dry-run 2>&1 | grep -E "===|BLOCKED|FAIL|DRY|ИТОГ" | cut -c1-220 | tail -c 2800;;
  run_check) NOX_SERVER=$SRV timeout 250 ./run_block1.sh --check 2>&1 | grep -E "===|PASS|FAIL|BLOCKED|ИТОГ" | cut -c1-220 | tail -c 2800;;
  run) NOX_SERVER=$SRV nohup setsid ./run_block1.sh > /root/nox/logs/block1_run.log 2>&1 < /dev/null & sleep 100; grep -E "===|PASS|FAIL|BLOCKED|ИТОГ" /root/nox/logs/block1_run.log | cut -c1-220 | tail -c 2600;;
  status) grep -E "===|PASS|FAIL|BLOCKED|ИТОГ" /root/nox/logs/block1_run.log | cut -c1-220 | tail -c 2600; echo ---; for f in /root/nox/receipts/*.json; do python3 -I -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["id"],d["result"],d.get("reason","")[:90])' "$f" 2>/dev/null; done | tail -40;;
  detail) for i in P1-06 P1-01; do echo "##### $i"; cat /root/nox/receipts/$i.json 2>/dev/null | head -12 | cut -c1-200; tail -n 12 /root/nox/logs/$i.log 2>/dev/null | cut -c1-200; done; pgrep -af "cmake|make|nvcc|llama" | head -5 | cut -c1-150; ls /root/nox/llama.cpp 2>/dev/null | head -3; df -h /root /dev/shm | tail -2;;
  canada) curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/canada/install_canada.sh?t=$RANDOM" -o /tmp/ic.sh && bash /tmp/ic.sh 2>&1 | cut -c1-200 | tail -c 2800;;
  unblock) echo "--before:"; ls -la /run/nox/ /run/nox/pause 2>/dev/null | head -20; ls /root/nox/run/maintenance* 2>/dev/null
    rm -f /run/nox/STOP /root/nox/STOP; for f in /run/nox/pause/*.lock; do [ -e "$f" ] || continue; p=$(basename "$f" .lock); kill -0 "$p" 2>/dev/null || rm -f "$f"; done
    rm -f /run/nox/maintenance* /root/nox/run/maintenance* 2>/dev/null; pkill -CONT -f "nox_|redo_worker" 2>/dev/null
    echo "--after:"; ls -la /run/nox/ 2>/dev/null | head; echo "--receipts BLOCKED/FAIL:"; grep -lE '"status": *"(BLOCKED|FAIL)' /root/nox/receipts/*.json 2>/dev/null | head -20
    echo "--services:"; for pt in 8081 8082 8083 8090; do echo -n "$pt "; curl -s -m3 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:$pt/health; done
    echo "--chat/gateway cfg:"; ls /root/nox/ | head -40; cat /root/nox/nox.env 2>/dev/null | sed 's/\(KEY\|TOKEN\|SECRET\)=.*/\1=***/' | head -20
    echo "--gpu:"; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader;;
  sizes) df -h /root /dev/shm | cat; for d in /root/s2_backup* /root/nox/backup_s2 /root/nox/backups /root/nox/memory /root/nox/receipts /root/nox/reports /root/nox/state /root/nox/events /root/nox/slots /root/nox/repo; do [ -e "$d" ] && du -sh "$d" 2>/dev/null; done; echo "--shards:"; ls -la /dev/shm/nox_glm | awk '{print $5, $9}' | tail -12; pgrep -af "curl.*gguf|redo_worker" | cut -c1-120 | head -5;;
  diskinv) df -h / | tail -1; echo "--top /root:"; du -xh --max-depth=1 /root 2>/dev/null | sort -rh | head -14; echo "--nox:"; du -xh --max-depth=1 /root/nox 2>/dev/null | sort -rh | head -22; echo "--dl/hf:"; du -xh --max-depth=2 /root/nox/dl 2>/dev/null | sort -rh | head -24; echo "--other:"; du -xsh /var/lib/apt /var/cache /var/log /tmp /root/.cache /root/.npm /usr/local /opt 2>/dev/null | sort -rh | head -8; echo "--biggest files:"; find /root /opt /workspace -xdev -type f -size +500M 2>/dev/null | head -20 | xargs -r ls -la | awk '{print $5, $9}';;
  diskclean) df -h / | tail -1; rm -rf /root/.nuget/packages /root/.nuget/NuGet 2>/dev/null; find /tmp -xdev -type f -mtime +1 -size +1M -delete 2>/dev/null; rm -rf /root/nox/dl/gh/*/.git /root/nox/dl/npm 2>/dev/null; apt-get clean 2>/dev/null; pip cache purge >/dev/null 2>&1; journalctl --vacuum-size=20M >/dev/null 2>&1; echo "--after:"; df -h / | tail -1; du -xsh /root/nox/extras /root/nox/dl/drive /usr/local /opt 2>/dev/null; ls /root/nox/extras | head -20; du -xh --max-depth=1 /usr/local /opt 2>/dev/null | sort -rh | head -8;;
  stopsweep) echo "--before:"; pgrep -af "glm_sweep|ik_llama/build/bin/llama-server" | cut -c1-140; pkill -f "/root/nox/glm_sweep.py"; sleep 1; pkill -f "ik_llama/build/bin/llama-server"; sleep 4; echo "--after:"; pgrep -af "glm_sweep|ik_llama/build/bin/llama-server|llama-server" | cut -c1-140; curl -s -m3 -o /dev/null -w "8081=%{http_code}\n" http://127.0.0.1:8081/health; nvidia-smi --query-gpu=memory.used --format=csv,noheader; free -g | sed -n 2p;;
  s1state) echo "--shards shm:"; ls -la /dev/shm/nox_glm 2>/dev/null | tail -14; echo "--disk:"; ls -la /root/nox/glm53_disk 2>/dev/null | tail -4; echo "--procs:"; pgrep -af "llama-server|glm_redo|aria2|hf_transfer|curl.*gguf|nox" | cut -c1-140 | head -12; echo "--health:"; curl -s -m3 http://127.0.0.1:8081/health; echo; curl -s -m3 http://127.0.0.1:8082/health | head -c 200; echo; tail -n 6 /root/nox/logs/glm_server.log 2>/dev/null | cut -c1-160; tail -n 4 /root/nox/logs/glm_redo*.log 2>/dev/null | cut -c1-160; free -g | head -2; cat /root/nox/run/server_probe.json 2>/dev/null | head -c 200;;
  gpu) curl -fsSL -H "Accept: application/vnd.github.raw" "https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox-control/gpu_tier/run.sh?ref=main" -o /tmp/gpu_run.sh && bash /tmp/gpu_run.sh 2>&1 | tail -c 2900;;
  *) echo "unknown mode $MODE";;
esac
