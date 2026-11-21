#!/bin/bash
D=/root/nox/dl; echo "== npm"; grep -cE "^OK" $D/logs/npm.log; grep -E "FAIL|NPM_DONE" $D/logs/npm.log
echo "== hf"; cat $D/logs/hf_all.log 2>/dev/null; du -sh $D/hf/* 2>/dev/null
echo "== gh"; cat $D/logs/gh.log 2>/dev/null | cut -c1-100 | tail -6
echo "== glm"; grep -E "ALL_OK|SOME_BAD" /root/nox/logs/redo.log; df -h /dev/shm | tail -1
