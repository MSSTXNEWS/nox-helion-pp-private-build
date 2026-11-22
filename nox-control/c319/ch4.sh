#!/bin/bash
echo "<<<$(tail -c +10001 /root/nox/flash_pack.b64 | head -c 2500)>>>"
