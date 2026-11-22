#!/bin/bash
date +%H:%M; ps -eo pid,etimes,pcpu,args | grep -E 'flash_ab4|llama-server.*8081' | grep -v grep | cut -c1-260
cut -c1-170 /root/nox/logs/flash_ab4.log | tail -14; ls -la --time-style=+%H:%M /root/nox/logs/flash_ab4.log | awk '{print $6}'
