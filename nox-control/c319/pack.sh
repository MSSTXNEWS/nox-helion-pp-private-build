#!/bin/bash
cd /root/nox/state && tar cJf /root/nox/flash_pack.txz FLASH_SPEED.json MODEL_SWAP.json ru_blind.md && base64 -w0 /root/nox/flash_pack.txz > /root/nox/flash_pack.b64; wc -c /root/nox/flash_pack.b64
