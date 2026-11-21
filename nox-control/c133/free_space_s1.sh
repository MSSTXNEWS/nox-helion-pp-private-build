#!/bin/bash
# по слову владельца: удалить только 4 перечисленных каталога (прошлая копия сайта, временный архив, неиспользуемые модели)
df -h / | tail -1
du -sh /root/nox/* 2>/dev/null | sort -h | tail -6
rm -rf /root/nox/web.old /root/nox/web_dl /root/nox/dl/hf/e5_small /root/nox/dl/hf/whisper_large_v3_turbo
echo "after:"; df -h / | tail -1
