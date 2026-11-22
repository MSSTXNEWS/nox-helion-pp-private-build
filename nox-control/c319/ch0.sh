#!/bin/bash
echo "<<<$(tail -c +1 /root/nox/flash_pack.b64 | head -c 2500)>>>"
