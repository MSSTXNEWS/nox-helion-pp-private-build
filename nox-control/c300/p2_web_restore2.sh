#!/bin/bash
echo "C300: p2_web_restore2"; B=/workspace/nox/backup
for d in nox-backup-20261125-0030 nox-backup-20261124-0030; do echo "## $d"; ls -la $B/$d | head -5; head -c 300 $B/$d/rel.txt 2>/dev/null; echo; grep -m6 -E 'ops/draw|invoke_draw' $B/$d/content_manifest.tsv | cut -c1-250; head -3 $B/$d/content_manifest.tsv | cut -c1-250; file $B/$d/part_000 | cut -c1-200; done
echo "## nox_backup.sh excerpt (how parts are made, restic)"; grep -nE 'tar|restic|split|zstd|gzip|RESTIC|password' $B/nox_backup.sh | sed -E 's/(PASSWORD|password)[=:][^ ]+/\1=REDACTED/' | cut -c1-200 | head -25
echo "## restic snapshots (read-only)"; which restic; ls $B/restic/snapshots | head -5
echo "## DONE"
