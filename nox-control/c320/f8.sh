#!/bin/bash
pgrep -af 'tune_worker|flash_try|flash_ab|glm_watch|flash_start' | cut -c1-120
ls -la --time-style=+%d-%H:%M /root/nox/flash_*.sh /root/nox/tune_worker.sh | awk '{print $6,$7}'
head -c 700 /root/nox/flash_try.sh; echo ...; head -c 500 /root/nox/glm_watch.sh
