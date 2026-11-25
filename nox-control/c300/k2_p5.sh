echo "C300: k2_p5"
S=/workspace/nox/web/site; cd $S
head -c 400 data/organs_hist.jsonl; echo; wc -l data/organs_hist.jsonl; ls data | head -20
grep -o '<main[^>]*>\|<section[^>]*class="[^"]*"' growth.html | head -8
grep -o 'id="[a-zA-Z0-9_-]*"' growth.html | head -20 | tr '\n' ' '; echo
grep -o 'class="[a-z]*msg[^"]*"\|class="[^"]*bubble[^"]*"\|class="[^"]*\bmsg\b[^"]*"' chat.html | sort | uniq -c | head
grep -o 'role-[a-z]*\|\.msg\.[a-z]*\|data-role="[a-z]*"' nox-chat-tg.js nox-chat-tg.css 2>/dev/null | sort | uniq -c | head
grep -o '<audio[^>]*>\|id="[a-zA-Z]*Audio[a-zA-Z]*"' music.html | head -3
grep -o 'id="[a-zA-Z0-9_-]*"' music.html | head -25 | tr '\n' ' '
exit 0
