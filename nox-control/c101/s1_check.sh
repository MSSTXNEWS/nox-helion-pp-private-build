#!/bin/bash
echo "== redo"; tail -n 14 /root/nox/logs/redo.log | cut -c1-160; pgrep -c curl; df -h /dev/shm | tail -1
echo "== pull"; tail -n 12 /root/nox/logs/pull.log | tr '\r' '\n' | grep -vE "^sftp|^$" | tail -9; ls -la /root/nox/backup_s2 | tail -9
