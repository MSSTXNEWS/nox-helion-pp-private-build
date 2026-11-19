#!/bin/sh
# Lightweight supervised heartbeat; never starts a new rclone when cgroup RAM is tight.
set -eu
umask 077
trap 'exit 0' TERM INT
while :
do
  if [ -f /sys/fs/cgroup/memory.max ] && [ -f /sys/fs/cgroup/memory.current ]
  then
    IFS= read -r limit < /sys/fs/cgroup/memory.max || limit=
    IFS= read -r current < /sys/fs/cgroup/memory.current || current=
    case "$limit:$current" in
      *[!0-9:]*|:*) sleep 600; continue ;;
    esac
    if [ "$limit" -le "$current" ] || [ "$((limit-current))" -lt 268435456 ]
    then
      sleep 600
      continue
    fi
  fi
  /usr/bin/python3 -B /root/nox/ops/drive-auth/nox_drive_reconnect.py --config /root/.config/rclone/rclone.conf --state-dir /var/lib/nox-drive-reconnect || :
  sleep 600
done
