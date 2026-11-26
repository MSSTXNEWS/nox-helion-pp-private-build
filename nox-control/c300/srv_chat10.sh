#!/bin/bash
F=/workspace/nox/web/pkg/server/chat_core.py
grep -n -E '"stage"|"race"|sleep|timeout|HEDGE|delay' $F | cut -c1-200 | head -40
