#!/bin/bash
echo "<<<$(tail -c +7501 /root/nox/flash_pack.b64 | head -c 2500)>>>"
