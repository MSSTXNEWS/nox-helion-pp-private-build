S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
ls vendor | tr '\n' ' '; echo; ls vendor/nox-fx vendor/arwes 2>&1 | head -20
grep -rl "nox-hud" --include=*.css --include=*.js . 2>/dev/null | head -5
grep -o '<select[^>]*>' voice.html | head; grep -n "<select" nox-voice*.js voice.html | head -5 | cut -c1-200
grep -o '<script[^>]*>' atlas.html | head -20; grep -o 'link[^>]*stylesheet[^>]*' atlas.html | wc -l
