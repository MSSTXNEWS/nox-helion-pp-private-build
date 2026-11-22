#!/bin/bash
W=/root/nox/web
grep -o "\['deep'.\{0,200\}" $W/nox_mode.js | head -2; grep -n "deep\|'max'" $W/nox_mode.js | cut -c1-170 | head -14
echo "== ws"; sed -n 176,224p /root/nox/web_server.py | cut -c1-210
