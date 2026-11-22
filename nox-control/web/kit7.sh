#!/bin/bash
S=/root/nox/soul_kit; P=/root/nox/repo/nox-control/qs6/soul_prompt_ru.txt
ls -l $P; wc -c $P; head -c 700 $P; echo; echo ---
sed -n 26,34p /root/nox/web_server.py | cut -c1-170
echo --- core; Z=$(ls $S/08_Live_Chat_Memory_Architecture/NOX_COGNITIVE_CORE_*.zip | head -1)
mkdir -p $S/cognitive_core && cd $S/cognitive_core && unzip -qn $Z && ls | head -20; find . -name "test*.py" | head -8; find . -name "*.bundle" -o -name "*.patch" | head -4; ls README* 2>/dev/null; python3 --version; python3 -c "import pytest" 2>&1 | tail -1
