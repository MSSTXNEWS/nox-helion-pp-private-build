#!/bin/bash
echo "<<<$(tail -c +17501 /root/nox/flash_pack.b64 | head -c 2500)>>>"
