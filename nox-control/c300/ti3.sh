#!/bin/bash
S=/workspace/nox/web/site; grep -o "[a-z-]*\.html'[^}]\{0,90\}" $S/nox-nav.js | head -30; echo ===; grep -o "{ *id: *'[a-z-]*'[^}]\{0,120\}" $S/nox-shell.js | head -20
tail -c 700 $S/cinema.html
