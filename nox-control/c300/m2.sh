#!/bin/bash
Q=/root/nox/repo/nox-control; ls $Q/qs6 | head -40 | tr '\n' ' '; echo
grep -n "def do_POST\|/api\|json.loads\|\"op\"\|'op'\|action\|query" $Q/qs6/recall_server.py | head -25 | cut -c1-160
echo "== gw uses"; grep -n "import\|recall\|memory\|s03\|MEMORY_DB" $Q/glm53/gateway.py | head -25 | cut -c1-150
