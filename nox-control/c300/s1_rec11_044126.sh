cd /workspace/nox/web/site/vendor
cat nox-liquid-glass/NOX-INTEGRATION.txt | head -40; head -c 1500 nox-liquid-glass/liquid-glass.js; echo; head -c 800 nox-liquid-glass/liquid-glass.css; wc -c nox-liquid-glass/*
ls nox-x/tone nox-x/vad nox-x/fx2; cat nox-x/vad/VERSION 2>/dev/null
grep -rl "liquid-glass\|LiquidGlass" /workspace/nox/web/site/*.html 2>/dev/null | head -3
grep -n "space\b\|id=\"space\"\|getContext\|--voice\|noxVoice\|__nox" /workspace/nox/web/site/nox-theme.js | head; ls /workspace/nox/web/sun_v1 | head; grep -rn "uniform\|u_[a-zA-Z]*" /workspace/nox/web/sun_v1/*.js 2>/dev/null | head -5 | cut -c1-160
