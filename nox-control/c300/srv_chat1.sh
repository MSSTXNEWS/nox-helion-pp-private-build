#!/bin/bash
N=/workspace/nox
echo "== ports"; ss -Htlnp 2>/dev/null | grep -E ':(8090|8091|8104|8141|8142|8143|8793|18230)\b' | awk '{print $4}' | sort | tr '\n' ' '
echo; echo "== 8104 cmd"; tr '\0' ' ' </proc/$(pgrep -f 'llama-server.*8104' | head -1)/cmdline 2>/dev/null | cut -c1-400
echo; echo "== donor_hybrid.cmd"; cat $N/state/donor_hybrid.cmd 2>/dev/null | cut -c1-400; ls $N/state/p3/ | head -30
echo "== restart_watch.sh"; cat $N/state/p3/restart_watch.sh 2>/dev/null | head -40
echo "== slots"; curl -s -m3 127.0.0.1:8104/slots | python3 -c "import sys,json;[print(s['id'],s['is_processing'],s.get('params',{}).get('n_predict')) for s in json.load(sys.stdin)]"
echo "== /api/turn refs"; grep -rn "api/turn" $N/brain/BRAIN/*.py $N/web_server.py 2>/dev/null | cut -c1-200 | head -8
echo "== free"; free -g | head -2; nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
