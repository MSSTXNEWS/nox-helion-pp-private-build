#!/bin/bash
sed -n 328,350p /workspace/nox/web/pkg/server/chat_core.py | cut -c1-260
grep -n "_pipe_after\|def _finish\|\"done\"" /workspace/nox/web/pkg/server/chat_core.py | cut -c1-200 | head
