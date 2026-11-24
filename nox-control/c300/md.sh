#!/bin/bash
M=/workspace/nox/models
inuse=$( (ps -eo args; cat /workspace/nox/router/*.yaml /workspace/nox/*/llama-swap*.y*ml /workspace/nox/*/*/llama-swap*.y*ml 2>/dev/null; find /workspace/nox -maxdepth 3 -name "*swap*.y*ml" -exec cat {} \; 2>/dev/null) | grep -o "/workspace/nox/models/[^ \"']*" | sort -u)
echo "$inuse" | sed 's#/workspace/nox/models/##' | cut -d/ -f1-3 | sort -u > /tmp/inuse.txt; echo "in-use refs: $(wc -l </tmp/inuse.txt)"
du -xh --max-depth=3 $M 2>/dev/null | sort -rh | sed -n 2,45p | while read sz p; do r=${p#$M/}; u=$(grep -c "^${r}" /tmp/inuse.txt 2>/dev/null); echo "$sz $r $([ "$u" -gt 0 ] && echo IN-USE)"; done
