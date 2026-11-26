#!/bin/bash
C=$(readlink /proc/2715440/cwd); echo cwd $C; ls $C | head -20
grep -rn -E "8104|max_tokens|Semaphore|concurr|workers|MAX_PAR|n_par" $C --include=*.py 2>/dev/null | grep -v bak | cut -c1-180 | head -25
grep -n "yield_chat" -r /workspace/nox/agent/nox_agents/*.py | cut -c1-170 | head -5
