set -x
N=/workspace/nox; S=$N/web/site; P=$N/svc/pipeline; B=$P/wow1; O=$N/state/c_wow1.out; : > $O
exec >> $O 2>&1
echo "== qa_audit result from acc3"; tail -c 2500 $N/state/c_acc3.out
echo "== install wow"; [ -f $S/chat.html.bak_c_wow ] || cp -p $S/chat.html $S/chat.html.bak_c_wow
cp $B/nox-chat-wow.js $B/nox-chat-wow.css $S/
grep -q nox-chat-wow.css $S/chat.html || sed -i 's#</head>#<link rel="stylesheet" href="./nox-chat-wow.css?v=w1">\n</head>#' $S/chat.html
grep -q nox-chat-wow.js $S/chat.html || sed -i 's#</body>#<script src="./nox-chat-wow.js?v=w1" defer></script>\n</body>#' $S/chat.html
grep -c "nox-chat-wow" $S/chat.html; curl -s -m5 -o /dev/null -w "wow.js http=%{http_code}\n" localhost:8091/web/nox-chat-wow.js
echo FINISHED
