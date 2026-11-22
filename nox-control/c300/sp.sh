#!/bin/bash
grep -n "Правила ответа" /root/nox/web_server.py | cut -c1-80; grep -o '_soul += ("\\n\\n\[Правила ответа[^)]*' /root/nox/web_server.py | head -1 | cut -c1-900
echo; grep -n "Ты — глубокий уровень" /root/nox/web_server.py | cut -c1-400
echo ==; head -c 2500 /root/nox/repo/nox-control/qs6/soul_prompt_ru.txt
