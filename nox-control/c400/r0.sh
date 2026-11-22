#!/bin/bash
cd /root/nox/dl/v7 2>&1 && find . -type f | head -40 | xargs ls -la --time-style=+ | awk '{print $5,$6}' | head -40
echo ---; ls /root/nox | head -40; echo ---
ls -la /root/nox/memory | head; echo ---
curl -s -m5 localhost:8095/health | head -c 300; echo; curl -s -m5 localhost:8081/health | head -c 200; echo
ss -ltnp 2>/dev/null | awk '{print $4,$6}' | grep -E ':80|:90|:81' | head -15
