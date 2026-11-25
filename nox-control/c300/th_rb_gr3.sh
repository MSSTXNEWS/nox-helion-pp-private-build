echo "C300: th_rb_gr3 (откат пакета gr3 к gr1)"
S=/workspace/nox/web/site; cd $S; TS=$(cat /workspace/nox/web/th_gr3.ts 2>/dev/null); [ -n "$TS" ] || { echo no_ts; exit 0; }
for f in nox-theme.js nox-graphite.css nox-graphite-map.css vendor/nox-x/filerobot/filerobot-image-editor.min.js; do [ -f $f.bak_th2_$TS ] && cp $f.bak_th2_$TS $f && echo restored $f; done; rm -f nox-th-fix.css; echo rolled_back_to_gr1
