#!/bin/bash
cd /workspace/nox/agent/nox_agents
grep -n -E "\.tmp|os\.replace|os\.rename" *.py mind/*.py 2>/dev/null | cut -c1-170 | head -30
