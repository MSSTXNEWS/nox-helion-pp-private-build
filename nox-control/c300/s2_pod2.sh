#!/bin/bash
S=/workspace/nox/svc; ID=$(cat /tmp/s2_podid)
for i in $(seq 1 24); do R=$(curl -s -m5 "http://127.0.0.1:18210/status?id=$ID"); echo "$i $R" | cut -c1-250; case "$R" in *'"ok"'*|*'"err"'*) break;; esac; sleep 10; done
ls -la $S/data/s2_podcast | tail -4; tail -8 $S/logs/s2_podcast.log | cut -c1-300
