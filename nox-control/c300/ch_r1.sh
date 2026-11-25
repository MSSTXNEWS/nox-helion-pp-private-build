echo "C300: ch_r1"
S=/workspace/nox/web/site
cd $S && find . -maxdepth 1 -type f \( -name '*.js' -o -name '*.css' -o -name 'chat.html' \) -printf '%s %f\n' | sort -k2 > /tmp/ch_sizes.txt
echo "== count"; wc -l < /tmp/ch_sizes.txt
echo "== MD5"; md5sum chat.html nox-chat-*.js nox-chat-*.css nox-dock-wow.js nox-vt.css nox-graphite.css nox-ds.css 2>/dev/null
echo "== chat.html tags"; grep -o '<\(script\|link\)[^>]*\(src\|href\)="[^"]*"' chat.html | sed 's/<script //;s/<link //' | tr '\n' ' ' | cut -c1-6000
echo; echo "== mock_qa"; ls -la /workspace/nox/state/mock_qa | head -20
echo "== demo"; ls $S | grep -i "demo\|note\|pad\|k8-meta\|nx-" | head -30
echo "== NOXNote"; grep -l "NOXNote" $S/*.js | head; 
echo "== pipeline dir"; ls /workspace/nox/svc/pipeline | head -30
echo "== health"; curl -s -m4 localhost:18217/health; echo; curl -s -m4 localhost:8200/running | cut -c1-300; echo
nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv 2>&1 | head -3
