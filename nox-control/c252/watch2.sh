#!/bin/bash
cut -c1-220 /root/nox/glm_watch.sh | head -40
tail -4 /root/nox/logs/glm_watch.log | cut -c1-200
ls /root/nox/gpu_tier 2>/dev/null; cat /root/nox/gpu_tier/glm.args 2>/dev/null | cut -c1-400
