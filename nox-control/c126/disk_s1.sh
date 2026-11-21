#!/bin/bash
# S1: только чтение - где место (ничего не удаляет)
df -h / /root /tmp 2>&1 | head -6
du -sh /root/nox/web /root/nox/web.old /root/nox/web_dl /root/nox/dl /root/nox/logs 2>/dev/null
du -sh /root/nox/* 2>/dev/null | sort -h | tail -8
