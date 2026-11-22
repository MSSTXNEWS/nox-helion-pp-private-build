#!/bin/bash
date -u +%T
wc -l /root/nox/flash.py; grep -n "llama-server\|8081\|parallel\|Popen\|def \|sleep" /root/nox/flash.py | tail -30 | cut -c1-230
echo ---; tail -4 /root/nox/logs/flash.log | cut -c1-160
ls -la /dev/shm/glm53f/*.gguf | cut -c20-140
