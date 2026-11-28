echo "K1: v3d_x3"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_v3d3_$cb; mkdir -p $T
cp -a $S/v2 $T/v2; for p in finance news calendar atlas pdf projects; do [ -f $S/$p.html ] && cp -a $S/$p.html $T/; done
W=/tmp/v3d_$cb; mkdir -p $W; curl -fsSL "$R/v3d.list?cb=$cb" -o $W/list || { echo NOLIST; exit 0; }
n=0; bad=0; while read f; do mkdir -p $W/$(dirname "$f"); curl -fsSL --retry 4 "$R/v3d/$f?cb=$cb" -o "$W/$f" && n=$((n+1)) || { bad=$((bad+1)); echo "dlfail $f"; }; done < $W/list
echo "downloaded=$n bad=$bad"; [ $bad = 0 ] || { echo ABORT; exit 0; }
cp -r $W/v2/* $S/v2/; cp $W/root/*.html $S/; echo "installed backup=$T"
for u in finance.html news.html calendar.html atlas.html pdf.html projects.html; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
echo "K1: v2s_x2"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_v2s_$cb; mkdir -p $T
for s in writer coder designer; do [ -d $S/$s ] && cp -a $S/$s $T/$s; done
W=/tmp/v2s_$cb; mkdir -p $W; curl -fsSL "$R/v2s.list?cb=$cb" -o $W/list || { echo NOLIST; exit 0; }
n=0; bad=0; while read f; do mkdir -p $W/$(dirname "$f"); curl -fsSL --retry 4 "$R/v2s/$f?cb=$cb" -o "$W/$f" && n=$((n+1)) || { bad=$((bad+1)); echo "dlfail $f"; }; done < $W/list
echo "downloaded=$n bad=$bad"; [ $bad = 0 ] || { echo ABORT; exit 0; }
for s in writer coder designer; do rm -rf $S/$s; cp -r $W/$s $S/$s; done; echo "installed backup=$T"
for u in writer/index.html writer/writer.js coder/index.html coder/coder.js designer/index.html designer/designer.js; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
echo "memlist $(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{"user_id":"role:writer"}' http://127.0.0.1:18091/api/nox/memory/list)"
echo END
