#!/bin/bash
echo "<<<$(tail -c +15001 /root/nox/flash_pack.b64 | head -c 2500)>>>"
