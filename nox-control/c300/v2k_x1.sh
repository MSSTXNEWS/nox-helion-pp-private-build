echo "K1: v2k_x1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/v2k; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_v2k_$cb; mkdir -p $T
for f in widgets.html music.html v1n/mini-nox.js; do [ -f $S/$f ] && { mkdir -p $T/$(dirname $f); cp -a $S/$f $T/$f; }; done; [ -d $S/v2 ] && cp -a $S/v2 $T/v2
W=/tmp/v2k_$cb; mkdir -p $W/fonts; ok=0
for k in 1 2 3 4; do fail=0
 for f in assistant.js board.js chunk-4E724EOX.js chunk-6OWKX7EX.js chunk-6TZ6AUSY.js chunk-DG7ZX5K5.js chunk-IKBRAUHY.js chunk-LUHD7C3B.js chunk-R2WEFIZZ.js chunk-W7QLLHSG.js chunk-YACMTK7M.js cinema.js constructor.js fonts/inter-cyrillic-wght-normal.woff2 fonts/inter-latin-wght-normal.woff2 fonts/jetbrains-mono-cyrillic-wght-normal.woff2 fonts/jetbrains-mono-latin-wght-normal.woff2 kit.css music.js photo.js scene.js training.js voice.js widgets.js  widgets.html music.html mini-nox.js; do curl -fsSL "$R/$f?cb=$cb$k" -o $W/$f || { fail=1; echo "dlfail $f"; }; done
 [ $fail = 0 ] && [ "$(sha256sum $W/widgets.js | cut -c1-16)" = 5f288a3bf0eb79ee ] && { ok=1; break; }; sleep 5; done
[ $ok = 1 ] || { echo STALE; exit 0; }
mkdir -p $S/v2; for f in assistant.js board.js chunk-4E724EOX.js chunk-6OWKX7EX.js chunk-6TZ6AUSY.js chunk-DG7ZX5K5.js chunk-IKBRAUHY.js chunk-LUHD7C3B.js chunk-R2WEFIZZ.js chunk-W7QLLHSG.js chunk-YACMTK7M.js cinema.js constructor.js fonts/inter-cyrillic-wght-normal.woff2 fonts/inter-latin-wght-normal.woff2 fonts/jetbrains-mono-cyrillic-wght-normal.woff2 fonts/jetbrains-mono-latin-wght-normal.woff2 kit.css music.js photo.js scene.js training.js voice.js widgets.js ; do mkdir -p $S/v2/$(dirname $f); cp $W/$f $S/v2/$f; done
cp $W/widgets.html $W/music.html $S/; cp $W/mini-nox.js $S/v1n/mini-nox.js; echo "installed backup=$T"
for u in widgets.html music.html v2/widgets.js v2/music.js v2/kit.css v1n/mini-nox.js; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
for u in img/health music/gen jf/System/Info/Public; do echo "probe $u $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/$u)"; done
echo END
