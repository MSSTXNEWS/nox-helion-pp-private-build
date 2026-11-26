# webroot_sync: web_unify_s1.sh делает cp -a pkg/webroot/. site/ и откатывает сайт к webroot. Синхронизируем site -> pkg/webroot (только рабочие файлы, без .bak), с бэкапом.
W=/workspace/nox/web; S=$W/site; P=$W/pkg/webroot; TS=$(date +%s)
[ -d $P ] || { echo "WEBROOT_SYNC: нет $P"; exit 0; }
BK=$W/pkg_webroot_bak_$TS; n=0; mkdir -p $BK
cd $S
for f in $(ls | grep -E '^(.*\.html|nox-.*\.(js|css|svg)|nav\.json|roles\.json|manifest\.json|sw\.js)$' | grep -v '\.bak'); do
  [ -f "$f" ] || continue
  if ! cmp -s "$f" "$P/$f"; then [ -f "$P/$f" ] && cp -p "$P/$f" "$BK/$f"; cp -p "$f" "$P/$f" && n=$((n+1)); fi
done
for d in vendor/lucide; do [ -d $S/$d ] && [ ! -d $P/$d ] && { mkdir -p $P/$(dirname $d) && cp -a $S/$d $P/$d && echo "synced dir $d"; }; done
[ -d $S/vendor/nox-x/filerobot ] && [ -f $S/vendor/nox-x/filerobot/fie-i18n.json ] && [ -d $P/vendor/nox-x/filerobot ] && ! cmp -s $S/vendor/nox-x/filerobot/fie-i18n.json $P/vendor/nox-x/filerobot/fie-i18n.json && { cp -p $S/vendor/nox-x/filerobot/fie-i18n.json $S/vendor/nox-x/filerobot/filerobot-image-editor.min.js $P/vendor/nox-x/filerobot/ && n=$((n+2)); }
echo "WEBROOT_SYNC: обновлено $n файлов, бэкап $BK ($(ls $BK | wc -l) шт.)"
