#!/bin/bash
S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server
echo "== GL1"; uname -m; ls /workspace/nox/svc | head -30; ls -d /workspace/nox/svc/glance* /workspace/nox/glance* /workspace/nox/web/build/glance* 2>&1 | head
echo "-- start_all"; head -c 1800 /workspace/nox/svc/start_all.sh; echo; echo "-- start_extra"; head -c 1200 /workspace/nox/svc/start_extra.sh
echo "-- svc_registry"; head -c 900 $P/svc_registry.json
echo "-- gh api"; curl -s -m 15 https://api.github.com/repos/glanceapp/glance/releases/latest | grep -o '"browser_download_url": *"[^"]*linux-amd64[^"]*"'
echo "-- persona refs"; grep -rln "persona" /workspace/nox --include=*.py --include=*.json --include=*.js -s 2>/dev/null | grep -v "node_modules\|/vendor/\|/build/" | head -15
echo "-- sysprompt"; grep -rn "system_prompt\|SYSTEM_PROMPT\|\"role\": *\"system\"\|'role': *'system'" /workspace/nox --include=*.py -s 2>/dev/null | grep -v "node_modules\|/venv/\|/build/" | cut -c1-200 | head -12
echo "-- settings tab fn"; grep -n "tabs\|renderTab\|const TABS\|id:'" $S/nox-settings-tabs.js | cut -c1-200 | head -25
