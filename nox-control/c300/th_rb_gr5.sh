echo "C300: th_rb_gr5 (откат gr5 к gr4)"
S=/workspace/nox/web/site; cd $S; TS=$(cat /workspace/nox/web/th_gr5.ts 2>/dev/null); BK=/workspace/nox/web/th_gr5_bak_$TS; [ -d "$BK" ] || { echo no_backup; exit 0; }
cp $BK/nox-*.js . ; cp $BK/nox-graphite.css $BK/nox-graphite-map.css . 2>/dev/null; echo rolled_back_to_gr4
