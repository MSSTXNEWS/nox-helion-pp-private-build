echo "C300: th_rb_gr2 (откат пакета gr2 к gr1)"
S=/workspace/nox/web/site; cd $S; TS=$(cat /workspace/nox/web/th_gr2.ts 2>/dev/null); [ -n "$TS" ] || { echo no_ts; exit 0; }
for f in nox-theme.js nox-graphite.css nox-graphite-map.css nox-nav.js nox-wow.js operators.html live.html; do [ -f $f.bak_th2_$TS ] && cp $f.bak_th2_$TS $f && echo restored $f; done; rm -f nox-icons.js; echo rolled_back_to_gr1
