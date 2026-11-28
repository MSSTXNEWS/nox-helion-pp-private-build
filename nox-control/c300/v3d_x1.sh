echo "K1: v3d_x1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_v3d_$cb; mkdir -p $T
cp -a $S/v1n $T/v1n; cp -a $S/v2 $T/v2; for p in widgets music cinema photo voice chat-dc; do [ -f $S/$p.html ] && cp -a $S/$p.html $T/; done
W=/tmp/v3d_$cb; mkdir -p $W; curl -fsSL "$R/v3d.list?cb=$cb" -o $W/list || { echo NOLIST; exit 0; }
n=0; bad=0; while read f; do mkdir -p $W/$(dirname "$f"); curl -fsSL --retry 4 "$R/v3d/$f?cb=$cb" -o "$W/$f" && n=$((n+1)) || { bad=$((bad+1)); echo "dlfail $f"; }; done < $W/list
echo "downloaded=$n bad=$bad"; [ $bad = 0 ] || { echo ABORT; exit 0; }
rm -rf $S/v1n; cp -r $W/v1n $S/v1n; cp -r $W/v2/* $S/v2/; cp $W/root/*.html $S/; echo "installed backup=$T"
for u in chat-dc.html v1n/ab.js v1n/mini.js v1n/mini-nox.js v2/kit-motion.js cinema.html photo.html voice.html music.html widgets.html v2/cinema.js; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
echo END
