#!/bin/bash
# Vast перезаписывает authorized_keys; пробуем отдельный файл (если sshd его читает)
K='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINqWy+HWe6ltKqsULniik9eySr+dJ4KdJekoYmaozQhV s1pull'
(sshd -T 2>/dev/null || /usr/sbin/sshd -T 2>/dev/null) | grep -iE "authorizedkeysfile|subsystem|passwordauth"
mkdir -p ~/.ssh; echo "restrict,command=\"internal-sftp -R\" $K" > ~/.ssh/authorized_keys2; chmod 600 ~/.ssh/authorized_keys2
ls -la ~/.ssh | head; grep -c s1pull ~/.ssh/authorized_keys ~/.ssh/authorized_keys2
