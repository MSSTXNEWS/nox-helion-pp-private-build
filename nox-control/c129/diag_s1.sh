#!/bin/bash
echo "== import log"; tail -n 12 /root/nox/logs/memory_import.log | cut -c1-220
echo "== redo"; grep -E "ALL_OK|SOME_BAD| OK| BAD" /root/nox/logs/redo.log | tail -6 | cut -c1-100; ls -la /dev/shm/nox_glm | head -12 | awk '{print $5,$9}'; df -h /dev/shm / | tail -2
echo "== glm log"; grep -vE "unused tensor" /root/nox/logs/glm_server.log | tail -5 | cut -c1-200
