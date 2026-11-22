#!/bin/bash
cd /root/nox
ls hf_restart.py restart_web.sh 2>&1 | head -3; grep -c "_hre" web_server.py; grep -n "^import\|^from" web_server.py | head -5 | cut -c1-150; grep -n "_NOXHF_LINE\|^_MSK\|^TAG\|def _trim_hist\|def _intent\|def _wait_resp" web_server.py | cut -c1-120
echo "== pages"; for p in $(ls web/*.html | xargs -n1 basename); do echo -n "$p:$(curl -s -m6 -o /dev/null -w %{http_code} http://127.0.0.1:8091/web/$p) "; done; echo
echo "== menu/templates/max"; ls web | head -60 | tr '\n' ' '; echo
grep -l "templates.html" web/*.js web/*.html 2>/dev/null | head; echo "max refs:"; grep -lE "Максимум|\"max\"|'max'" web/*.js web/*.html 2>/dev/null | head
grep -o "Максимум[^<\"']\{0,30\}" web/*.html web/*.js 2>/dev/null | head -5
grep -n "nox_mode" web/*.js 2>/dev/null | cut -c1-160 | head -8
