S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
ls vendor/arwes-frames vendor/arwes-animated | head -30
grep -n -i "arwes" vendor/VENDOR_INDEX.md | head -8 | cut -c1-300
head -c 1800 vendor/nox-fx/hud.js; echo; grep -n "nox-hud" nox-fx.css | head -8 | cut -c1-200
grep -n "hud" index.html chat.html system.html | head -5 | cut -c1-160
grep -n "select" nox-voice-x.js | head -12 | cut -c1-200
