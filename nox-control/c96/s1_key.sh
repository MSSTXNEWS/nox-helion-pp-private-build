#!/bin/bash
# S1: ключ для вытягивания бэкапа с S2 (только этот ключ, на S2 будет read-only sftp)
mkdir -p /root/nox/backup_s2 ~/.ssh; [ -f ~/.ssh/s2pull ] || ssh-keygen -q -t ed25519 -N "" -f ~/.ssh/s2pull
cat ~/.ssh/s2pull.pub
echo "== shm"; df -h /dev/shm / | tail -2; ls -la /dev/shm/nox_glm /root/nox/glm53_disk | head -20
