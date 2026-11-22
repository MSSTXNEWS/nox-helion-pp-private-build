#!/bin/bash
for f in FLASH_SPEED.json MODEL_SWAP.json ru_blind.md; do echo "@@@BEGIN $f"; cat /root/nox/state/$f; echo; echo "@@@END $f"; done
