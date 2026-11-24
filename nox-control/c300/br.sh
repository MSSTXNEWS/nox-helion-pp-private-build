#!/bin/bash
f=/workspace/nox/integration/drive_media_20261123/bridge.py; grep -nE 'path ?== ?"|startswith\("/|def (do_|download|fetch|list)|googleapis|files\.get|alt=media|token' $f | head -25 | cut -c1-170
ls /workspace/nox/integration/drive_media_20261123 | head; cat /tmp/c300_ov 2>/dev/null
