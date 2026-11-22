#!/bin/bash
cat /root/nox/start_glm.sh | cut -c1-500; echo ---; cat /root/nox/glm_watch.sh | cut -c1-300 | head -30; echo ---; cat /root/nox/logs/flash_ab.log | cut -c1-200
