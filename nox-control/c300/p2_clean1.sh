#!/bin/bash
# P2 cleanup: caches (pip/npm), /tmp regular files >180min not open and not lock/pid/sock. Touches nothing else.
df -B1 /workspace / | awk 'NR>1{print "BEFORE",$6,$4}'
echo "## SIZES"; du -sh /root/.cache/pip /root/.npm /workspace/.hf_home /root/.cache/huggingface /workspace/.cache /workspace/.venv-backups /tmp 2>/dev/null
du -xh --max-depth=1 /workspace/nox 2>/dev/null | sort -rh | head -25
echo "## PIP/NPM"
pip cache purge 2>&1 | tail -2; /workspace/nox/venv/bin/pip cache purge 2>&1 | tail -2; npm cache clean --force 2>&1 | tail -2
echo "## TMP"
N0=$(du -sb /tmp 2>/dev/null | cut -f1)
OPEN=$(mktemp); (ls -l /proc/[0-9]*/fd /proc/[0-9]*/cwd 2>/dev/null | grep -o '/tmp/[^ ]*' | sort -u) > $OPEN
LIST=$(mktemp)
find /tmp -xdev -mindepth 1 -type f -mmin +180 ! -name '*.lock' ! -name '*.pid' ! -name '*.sock' ! -name 'c300*' -print 2>/dev/null > $LIST
cnt=0
while read -r f; do
  grep -qxF "$f" $OPEN && continue
  d=$(dirname "$f"); grep -qF "$d" $OPEN && continue
  rm -f -- "$f" && cnt=$((cnt+1))
done < $LIST
find /tmp -xdev -mindepth 1 -type d -empty -mmin +180 -delete 2>/dev/null
N1=$(du -sb /tmp 2>/dev/null | cut -f1)
echo "tmp removed files=$cnt freed_MB=$(( (N0-N1)/1048576 ))"
df -B1 /workspace / | awk 'NR>1{print "AFTER",$6,$4}'
echo "## DONE"
