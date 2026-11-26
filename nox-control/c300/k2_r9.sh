echo "C300: k2_r9"
N=/workspace/nox; W=$N/web/pkg/server
echo "--- chat_core 355-440"; sed -n 355,440p $W/chat_core.py | cut -c1-260
echo "--- draw refs"; grep -nE "нарисуй|img/generate|рису" $W/chat_core.py | cut -c1-230 | head -20
grep -nE "img/generate|/img/" $W/web_server.py | cut -c1-200 | head
echo "--- image_service"; wc -l $N/imgsvc/image_service.py; grep -nE "invoke|flux|FLUX|steps|torch.compile|port|def |OWNER" $N/imgsvc/image_service.py | cut -c1-200 | head -60
ps -eo pid,etimes,args | grep -E "image_service|imgsvc" | grep -v grep | cut -c1-200
