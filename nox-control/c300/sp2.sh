#!/bin/bash
grep -n "_md =\|_md=" /root/nox/web_server.py | cut -c1-200
grep -o "fetch('[^']*'" /root/nox/web/nox-wow.js | sort | uniq -c | head; grep -o "nox_mode[^,;]\{0,60\}\|mode: *[a-zA-Z.]*" /root/nox/web/nox-wow.js | sort | uniq -c | head
grep -o "Слышу вас[^'\"]*" /root/nox/web/*.js | head -3
