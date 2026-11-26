#!/bin/bash
B=/workspace/nox/backup; du -sh $B; ls -lt --time-style=+%F_%H:%M -s -h $B | head -12
tail -4 /workspace/nox/agent/out/backup.log | cut -c1-200
