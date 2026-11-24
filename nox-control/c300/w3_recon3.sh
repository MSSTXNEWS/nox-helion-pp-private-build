S=/workspace/nox/web/site; cd $S
echo ==TAIL; tail -c 3500 chat.html | cut -c1-600
echo ==VENDOR; ls vendor/nox-lib vendor/nox-extra vendor/nox-wow vendor/lottie-web vendor/fx vendor/glasskit vendor/loquix 2>/dev/null | head -80
find vendor lib -maxdepth 3 \( -iname "*marked*" -o -iname "*highlight*" -o -iname "*shiki*" -o -iname "*markdown*" -o -iname "*purify*" -o -iname "*dompurify*" \) 2>/dev/null | head
echo ==FB; sed -n '1,60p' /workspace/nox/web/pkg/server/liska_feedback.py 2>/dev/null || find /workspace/nox -name liska_feedback.py | head
echo ==FBFILES; ls -la /workspace/nox/state/ | head -30
