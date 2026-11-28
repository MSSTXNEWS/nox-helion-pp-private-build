echo "K1: s6l_e1"
N=/workspace/nox
F=$(grep -rl "chat_gate.log" $N/web/pkg/server $N/mods --include=*.py 2>/dev/null | head -5); echo "files: $F"
for f in $F; do echo "== $f lines=$(wc -l < $f) md5=$(md5sum < $f | cut -c1-8)"; grep -n "chat_gate.log\|def .*gate\|повтор прошлого ответа\|ассистентский шаблон\|just_model\|how=" $f | cut -c1-170 | head -30; done
echo END
