#!/bin/bash
C=/workspace/nox/cascade; ls $C | head -20
grep -rn -E "8104|Semaphore|concurr|MAX_PAR|max_par|parallel|threads|workers|max_tokens" $C --include=*.py --include=*.json --include=*.env --include=*.yaml 2>/dev/null | grep -v -E "bak|venv" | cut -c1-170 | head -30
tr '\0' ' ' </proc/2715440/environ | tr ' ' '\n' | grep -E "^NOX_|CASC" | sed -E 's/(KEY|TOKEN)=.*/\1=***/' | head -20
