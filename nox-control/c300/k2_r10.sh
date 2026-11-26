echo "C300: k2_r10"
N=/workspace/nox; W=$N/web/pkg/server
echo "--- нарис refs"; grep -rnE "нарис|draw" $W/chat_core.py $W/web_server.py | cut -c1-240 | head -25
grep -rln "invoke_draw" $N --include=*.py 2>/dev/null | grep -v -E "venv|\.bak|invoke_root" | head
F=$(find $N -name invoke_draw.py -not -path "*/venv/*" | head -1); echo "F=$F"; wc -l $F; sed -n 1,140p $F | cut -c1-220
echo "--- sd.cpp"; ls $N/imgsvc $N/bin 2>/dev/null | head -40
