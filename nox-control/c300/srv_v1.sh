#!/bin/bash
P=$(readlink /proc/523234/cwd); echo $P; tr '\0' ' ' </proc/523234/cmdline | cut -c1-150; echo
ls $P | head -30
grep -n -E "def verdict|/verdict|max_tokens|timeout|8141|8142|8104|8144|8300|ddgs|MiniCheck|Semaphore|ThreadPool" $P/*.py 2>/dev/null | grep -v "^.*#" | cut -c1-190 | head -50
