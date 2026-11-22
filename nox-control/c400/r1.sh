#!/bin/bash
cd /root/nox/dl/v7; find . -type f \( -name 'conscience.py' -o -name 'nox_core.py' -o -name 'soul_prime*' -o -name 'S1_0*' -o -name '*OPT*' -o -name 'probe_pv01*' \) -printf '%s %p\n' | head -30
echo ---; ls /root/nox/memory /root/nox/bin | head -30
echo ---; curl -s -m5 localhost:8095/health | head -c 300; echo; curl -s -m5 localhost:8081/health | head -c 100; echo
ss -ltnp 2>/dev/null | awk '{print $4,$6}' | grep -E ':(80|90|81|82)' | cut -c1-80 | head -15
ls /root/nox/brain 2>/dev/null | head; find /root/nox -maxdepth 2 -name 'conscience*' -o -maxdepth 2 -name 'nox_core*' | head
