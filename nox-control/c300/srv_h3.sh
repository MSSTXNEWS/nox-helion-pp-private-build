#!/bin/bash
F=/workspace/nox/web/pkg/server/chat_core.py
grep -n "meta2" $F | cut -c1-220
