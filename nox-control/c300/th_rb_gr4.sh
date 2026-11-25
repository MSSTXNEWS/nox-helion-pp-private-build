echo "C300: th_rb_gr4 (откат gr4 к gr3)"
S=/workspace/nox/web/site; cd $S; TS=$(cat /workspace/nox/web/th_gr4.ts 2>/dev/null); [ -n "$TS" ] || { echo no_ts; exit 0; }
for f in nox-theme.js nox-graphite.css nox-graphite-map.css nox-th-fix.css vendor/nox-x/filerobot/filerobot-image-editor.min.js; do [ -f $f.bak_th4_$TS ] && cp $f.bak_th4_$TS $f && echo restored $f; done; rm -f vendor/nox-x/filerobot/fie-i18n.json; echo rolled_back_to_gr3
