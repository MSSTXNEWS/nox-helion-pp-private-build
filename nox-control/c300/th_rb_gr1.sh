echo "C300: th_rb_gr1 (откат темы Графит)"
S=/workspace/nox/web/site; cd $S; TS=$(cat /workspace/nox/web/th_gr1.ts 2>/dev/null); [ -n "$TS" ] || { echo no_ts; exit 0; }
for f in nox-theme.js nox-wow-bg.js nox-ds.js nox-actions.js; do [ -f $f.bak_th_$TS ] && cp $f.bak_th_$TS $f && echo restored $f; done
rm -f nox-graphite.css nox-graphite-map.css; echo rolled_back
