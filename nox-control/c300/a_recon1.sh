S=/workspace/nox/web/site
echo "== html"; ls $S/*.html | xargs -n1 basename | tr '\n' ' '
echo; echo "== vendor"; ls $S/vendor 2>/dev/null | head -60
echo "== js/css"; ls $S | grep -E "\.(js|css)$" | tr '\n' ' '
echo; echo "== chat files"; wc -c $S/chat.html $S/nox-chat-x.js $S/index.html 2>&1
echo "== tools"; ls /workspace/nox/tools /workspace/nox/tools/node/bin 2>&1 | head -20
echo "== logs"; ls /workspace/nox /workspace/nox/logs 2>&1 | head -60
find /workspace -maxdepth 4 \( -iname "*train*log*" -o -iname "trainer_state.json" -o -iname "*.tfevents*" -o -iname "train*.jsonl" \) 2>/dev/null | head
echo "== stats"; curl -s -m5 127.0.0.1:8091/glm/v1/nox/stats | head -c 1500
echo; echo "== net"; curl -sI -m8 https://raw.githubusercontent.com/tsparticles/tsparticles/main/LICENSE | head -1; curl -sI -m8 https://registry.npmjs.org/gsap | head -1
df -h /workspace | tail -1; free -g | head -2
echo "== pinned"; python3 -c "print(open('/workspace/nox/qa_ctl.py').read()[:1200])"
echo "== qa"; cat $S/qa/audit.json 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print({k:(v.get('status'),v.get('wow')) for k,v in d.items()})"
