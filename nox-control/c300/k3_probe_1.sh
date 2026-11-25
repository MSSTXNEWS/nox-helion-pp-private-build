echo "C300: k3_probe_1"
S=/workspace/nox/web/site; cd $S
ls nox-chat-fx.js nox-cmd.js nox-ninja.js 2>&1; ls vendor | tr '\n' ' ' | head -c 3000; echo
ls /tmp/k2_qa.py 2>&1
for p in voice chat finance knowledge news; do echo "== $p"; wc -c $p.html; grep -o '<script[^>]*src="[^"]*"' $p.html | sed 's/.*src=//' | tr '\n' ' ' | head -c 900; echo; grep -o 'id="[^"]*"' $p.html | head -60 | tr '\n' ' ' | head -c 1500; echo; done
echo "== chatfx"; head -c 1500 nox-chat-fx.js; grep -n "voice\|orb" nox-chat-fx.js | head -20
echo "== cmd"; grep -o "NOXcmd[^;]\{0,80\}" nox-cmd.js | head -10
echo "== ninja"; grep -n "ninja-keys\|\.data\s*=" nox-ninja.js | head -10
echo "== qa"; head -c 2500 /tmp/k2_qa.py
exit 0
