#!/bin/bash
cd /root/nox
grep -rl "чистого листа" --include=*.py --include=*.js --include=*.html . 2>/dev/null | grep -v "\.bak" | head
grep -n "Запросы удалены" web_server.py repo/nox-control/glm53/*.py repo/nox-control/wow7/brain/*.py 2>/dev/null | cut -c1-200
