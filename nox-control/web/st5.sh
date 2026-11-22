#!/bin/bash
cd /root/nox
echo "web 'чистого листа': $(grep -c 'чистого листа' web_server.py)"; grep -n "_DEL\|def _clear" web_server.py | cut -c1-110 | head -5
cd repo/nox-control/wow7; sed -n 25,40p brain/organs.py | cut -c1-150; sed -n 138,148p brain/organs.py | cut -c1-170
echo "core actions refs: $(grep -c actions brain/nox_core.py)"; grep -n "actions" brain/nox_core.py | cut -c1-150
ls -la --time-style=+%F_%T PRIME prime | awk '{print $5,$6,$7}' | head -12; cmp -s PRIME/soul_prime_v3.txt prime/soul_prime_v3.txt && echo same_PRIME_prime
echo "greeting-rule lines in prime soul: $(grep -c 'приветств' prime/soul_prime_v3.txt)"
grep -n "^def \|^class " brain/actions.py | cut -c1-120 | head -20
