#!/bin/bash
S=/workspace/nox/web/site
cd $S
echo "#### nox_cmd.py"; cat /workspace/nox/web/pkg/server/nox_cmd.py | head -150
echo "#### registry"; ls -la qa/registry.json 2>&1; head -c 1500 qa/registry.json 2>&1
echo "#### nox-cmd.js"; cat nox-cmd.js
echo "#### nox-pult.js"; cat nox-pult.js
echo "#### nox-ninja.js"; cat nox-ninja.js
echo "#### dock cats"; grep -n "КОНСТРУКТОР\|КИНОТЕАТР\|ВИДЖЕТЫ" nox-dock.js | head; 
echo "#### sun"; cat nox-sun-x.js | head -60
echo "#### settings.html"; cat settings.html | cut -c1-300
echo "#### tabs"; cat nox-settings-tabs.js | cut -c1-400
echo "#### cmd_log"; tail -3 /workspace/nox/state/cmd_log.jsonl 2>&1 | cut -c1-300
