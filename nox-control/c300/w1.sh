#!/bin/bash
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL $R/w1.py -o /tmp/w1.py && python3 /tmp/w1.py && python3 /root/nox/restart_same.py 8091 | tail -1
# W038/W070: эмбеддинги с ядер быстрой модели на 34-39
for p in $(pgrep -f embed_server.py); do taskset -apc 34-39 $p >/dev/null && renice -n 10 -p $p >/dev/null; echo "embed $p -> $(taskset -cp $p | awk '{print $NF}')"; done
sed -i 's/taskset -c 28-33 \(\/root\/.nox-voice-venv\/bin\/python \/root\/nox\/embed_server.py\)/nice -n 10 taskset -c 34-39 \1/' /root/onstart.sh; grep -c "34-39" /root/onstart.sh
curl -fsSL $R/mtp.sh -o /root/nox/mtp_ab.sh && (nohup setsid bash /root/nox/mtp_ab.sh >/dev/null 2>&1 </dev/null &) && echo mtp started
