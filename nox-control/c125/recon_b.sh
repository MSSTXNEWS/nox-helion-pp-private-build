#!/bin/bash
# разведка: V21_24_LIBS и V21_RUNTIME_VENDOR_20 (верхние уровни + README/манифесты)
X=/root/nox/dl/drive/x
for d in V21_24_LIBS V21_RUNTIME_VENDOR_20; do echo "## $d"; (cd $X/$d && ls; find . -maxdepth 2 -mindepth 2 | head -40 | tr '\n' ' '); echo; done
ls $X/V21_RUNTIME_VENDOR_20/* 2>/dev/null | head -3 >/dev/null
find $X/V21_RUNTIME_VENDOR_20 -iname "*.md" -o -iname "*.json" | head -5
