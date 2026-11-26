#!/bin/bash
F=/workspace/nox/web/pkg/server/chat_core.py
grep -n -E "def _le_num|def _le\b|def _le\(" -A8 $F | cut -c1-220 | head -30
grep -rn "race_s" /workspace/nox/state /workspace/nox/web/pkg --include=*.json --include=*.py --include=*.cfg 2>/dev/null | grep -v bak | cut -c1-200 | head
