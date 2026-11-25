#!/bin/bash
echo "C300: p2_web_diag3"; D=/workspace/nox/web/pkg/server
echo "## find invoke_draw"; find /workspace /tmp /root -xdev -name 'invoke_draw*' 2>/dev/null | head -20
echo "## chat_core head"; sed -n 1,20p $D/chat_core.py | cut -c1-200
echo "## server dir invoke*"; ls -la --time-style=long-iso $D | grep -iE 'invoke|draw|img' | head
echo "## who references invoke_draw"; grep -rln 'invoke_draw' /workspace/nox --include=*.py --include=*.sh --include=*.json 2>/dev/null | head -10
echo "## diff bak_n_1 vs current (head)"; diff $D/chat_core.py.bak_n_1 $D/chat_core.py | head -40 | cut -c1-200
echo "## bak_n_1 imports"; sed -n 1,16p $D/chat_core.py.bak_n_1 | cut -c1-160
echo "## all chat_core baks"; ls -la --time-style=long-iso $D | grep 'chat_core' | cut -c1-120
echo "## DONE"
