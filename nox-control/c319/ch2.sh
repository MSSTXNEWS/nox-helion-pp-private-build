#!/bin/bash
echo "<<<$(tail -c +5001 /root/nox/flash_pack.b64 | head -c 2500)>>>"
