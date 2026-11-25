echo "C300: th_rb_gr6 (откат gr6 к gr5)"
S=/workspace/nox/web/site; cd $S; TS=$(cat /workspace/nox/web/th_gr6.ts 2>/dev/null); BK=/workspace/nox/web/th_gr6_bak_$TS; [ -d "$BK" ] || { echo no_backup; exit 0; }
cp $BK/nox-*.js $BK/live.html . ; cp $BK/nox-graphite.css $BK/nox-graphite-map.css . 2>/dev/null; echo rolled_back_to_gr5
