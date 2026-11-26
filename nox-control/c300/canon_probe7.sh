#!/bin/bash
echo "C300: canon_probe7"
N=/workspace/nox
which rclone age 2>&1 | head -2
grep -n 'rclone\|RCLONE\|age ' $N/agent/nox_backup.sh | sed -E 's/[A-Za-z0-9_-]{24,}/<ID>/g' | cut -c1-200 | head -20
rclone listremotes 2>&1 | head -5
