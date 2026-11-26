#!/bin/bash
N=/workspace/nox
sed -n 1,16p $N/agent/nox_backup.sh | cut -c1-200
B=$(grep -m1 '^B=' $N/agent/nox_backup.sh); echo "$B"
eval "$(grep -m1 '^NOXD=' $N/agent/nox_backup.sh)"; eval "$B" 2>/dev/null; echo "B=$B"
du -sh "$B" 2>/dev/null; ls -lt --time-style=+%F_%H:%M "$B" | head -14
