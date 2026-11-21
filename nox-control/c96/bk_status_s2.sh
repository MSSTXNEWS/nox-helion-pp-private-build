#!/bin/bash
tail -4 /root/nox/logs/bk.log; ls -la /root/nox/backup_final | head -14; cat /root/nox/backup_final/SHA256SUMS 2>/dev/null | head
