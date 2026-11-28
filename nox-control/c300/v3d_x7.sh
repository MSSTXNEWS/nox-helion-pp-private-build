echo "K1: v3d_x7"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_v3d7_$cb; mkdir -p $T
cp -a $S/v2 $T/v2; for p in advisors ai-learning assistant atlas board browser calendar calls cinema connections constructor contacts downloads evolution finance forge g01-status g02-owner g03-release g04-provider g05-evidence g06-orchestrator g07-hardware games home index knowledge mail marketing memory messenger mini music news ops pc-control pc-maintenance pdf photo projects scene social spaces training voice weights widgets ; do [ -f $S/$p.html ] && cp -a $S/$p.html $T/; done
W=/tmp/v3d_$cb; mkdir -p $W; curl -fsSL "$R/v3d.list?cb=$cb" -o $W/list || { echo NOLIST; exit 0; }
n=0; bad=0; while read f; do mkdir -p $W/$(dirname "$f"); curl -fsSL --retry 4 "$R/v3d/$f?cb=$cb" -o "$W/$f" && n=$((n+1)) || { bad=$((bad+1)); echo "dlfail $f"; }; done < $W/list
echo "downloaded=$n bad=$bad"; [ $bad = 0 ] || { echo ABORT; exit 0; }
cp -r $W/v2/* $S/v2/; cp $W/root/*.html $S/; echo "installed backup=$T"
for u in $(ls $W/root | sed 's/^//'); do echo "$u $(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:18091/web/$u)"; done
echo END
