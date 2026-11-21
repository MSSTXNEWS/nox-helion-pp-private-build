#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-200; }
echo "== eval_suite"; sed -n 1,18p /root/nox/scripts/eval_suite.py | a; ls /root/nox/eval 2>/dev/null | head -8
echo "== ram/cpu/nvme"; free -g | awk 'NR==2{print "RAM total/free GB",$2,$4}'; nproc; lsblk -dno NAME,SIZE,ROTA 2>/dev/null | head -5; df -h /root /tmp | awk 'NR>1{print $1,$2,$4}'
echo "== big dirs (read-only)"; du -xh --max-depth=2 /root 2>/dev/null | sort -rh | head -14
echo "== reclaimable candidates"; find /root -xdev \( -name "step-*" -o -name "*.bak*" -o -name "archive_*" -o -name "*.pt" -o -name "*.safetensors" \) -size +300M 2>/dev/null | head -12
