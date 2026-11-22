#!/bin/bash
echo "<<<$(tail -c +2501 /root/nox/flash_pack.b64 | head -c 2500)>>>"
