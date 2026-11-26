echo "C300: ch_dc22"
S=/workspace/nox/web/site; ls -la $S/vendor/nox-liquid-glass | head; wc -c $S/vendor/nox-liquid-glass/*.css $S/nox-fx-lg.css $S/nox-fx-lg.js 2>&1 | head
echo "== css"; head -c 2200 $S/vendor/nox-liquid-glass/liquid-glass.css | cut -c1-400
echo "== js refs"; grep -l "lg-layer" $S/*.js $S/vendor/nox-liquid-glass/* 2>/dev/null | head; grep -n -o ".\{0,80\}lg-layer.\{0,160\}" $S/nox-fx-lg.js $S/nox-fx.js 2>/dev/null | head -4 | cut -c1-300
