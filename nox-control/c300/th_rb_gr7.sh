echo "C300: th_rb_gr7 (откат gr7 к gr6: слой движения)"
S=/workspace/nox/web/site; cd $S; TS=$(cat /workspace/nox/web/th_gr7.ts 2>/dev/null); BK=/workspace/nox/web/th_gr7_bak_$TS; [ -d "$BK" ] || { echo no_backup; exit 0; }
cp $BK/nox-*.js $BK/live.html . ; cp $BK/nox-graphite.css $BK/nox-graphite-map.css . 2>/dev/null; rm -f nox-motion.css nox-motion.js; echo rolled_back_to_gr6
