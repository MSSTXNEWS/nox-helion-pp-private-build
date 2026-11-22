#!/bin/bash
cd /root/nox/repo/nox-control/wow7
grep -n "soul_prime\|SOUL\|PRIME\|prime" brain/nox_core.py brain/organs.py brain/executors.py brain/core_view.py 2>/dev/null | cut -c1-190 | head -40
ls prime; grep -n "def load_soul" -A8 ../qs6/prompt_builder.py | cut -c1-150
echo == web chat path; sed -n 309,420p /root/nox/web_server.py | cut -c1-200
