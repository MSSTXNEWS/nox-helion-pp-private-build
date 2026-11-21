#!/bin/bash
cd /root/nox/backup_s2 && sha256sum -c SHA256SUMS 2>&1 | cut -c1-80; du -sh .; df -h / | tail -1
