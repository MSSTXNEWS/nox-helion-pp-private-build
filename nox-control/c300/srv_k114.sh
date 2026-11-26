echo "C300: srv_k114"
cd /workspace/nox
sed -n 160,250p ops/draw/invoke_draw.py | cut -c1-230
echo "--- web img route"; grep -n "img/generate" web_server.py 2>/dev/null | head -3
(timeout 150 du -x -k --max-depth=3 /workspace 2>/dev/null | sort -rn | head -45 | awk '{printf "%.1fGB %s\n",$1/1048576,$2}') 
