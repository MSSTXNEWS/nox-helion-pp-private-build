#!/bin/bash
grep -rln -E "\"race\"" /workspace/nox --include=*.py 2>/dev/null | grep -v -E "bak|tmp|venv|tests" | head
