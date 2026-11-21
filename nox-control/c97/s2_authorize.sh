#!/bin/bash
# S2: ключ S1 только для чтения бэкапа (read-only sftp, без shell/forwarding)
K='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINqWy+HWe6ltKqsULniik9eySr+dJ4KdJekoYmaozQhV s1pull'
mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; grep -q "s1pull" ~/.ssh/authorized_keys || echo "restrict,command=\"internal-sftp -R\" $K" >> ~/.ssh/authorized_keys
tail -n1 ~/.ssh/authorized_keys | cut -c1-120; grep -c . ~/.ssh/authorized_keys
