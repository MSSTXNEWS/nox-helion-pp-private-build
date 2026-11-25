#!/bin/bash
S=/workspace/nox/web/site
echo "C300: k2_probe"
ls $S | grep -E '\.html$' | tr '\n' ' '; echo
ls $S | grep -E '^nox-k2' | tr '\n' ' '; echo
df -h /workspace | tail -1
grep -n "nox-ds\|<script" $S/voice.html | cut -c1-160 | head -30
head -c 1500 $S/nox-cmd.js 2>/dev/null; grep -o "NOXcmd\.[a-zA-Z]*" -h $S/*.js | sort | uniq -c | sort -rn | head -8
ls $S/qa/rework | head
