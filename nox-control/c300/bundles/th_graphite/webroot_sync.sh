# webroot_sync: web_unify_s1.sh делает cp -a pkg/webroot/. site/ и откатывает сайт к webroot. Синхронизируем site -> pkg/webroot (только рабочие файлы, без .bak), с бэкапом.
W=/workspace/nox/web; S=$W/site; P=$W/pkg/webroot; TS=$(date +%s)
[ -d $P ] || { echo "WEBROOT_SYNC: нет $P"; exit 0; }
BK=$W/pkg_webroot_bak_$TS; n=0; mkdir -p $BK
cd $S
for f in $(ls | grep -E '^(.*\.html|nox-.*\.(js|css|svg)|nav\.json|roles\.json|manifest\.json|sw\.js)$' | grep -v '\.bak'); do
  [ -f "$f" ] || continue
  if ! cmp -s "$f" "$P/$f"; then [ -f "$P/$f" ] && cp -p "$P/$f" "$BK/$f"; cp -p "$f" "$P/$f" && n=$((n+1)); fi
done
# done_10.sh (agent, 22.11) при перезапуске делает cp -a pkg/webroot/. site/ && cp -a pkg/vendor site/ -> vendor тоже синхронизируем
PV=$W/pkg/vendor
if [ -d $PV ]; then
  [ -d $S/vendor/lucide ] && [ ! -d $PV/lucide ] && { cp -a $S/vendor/lucide $PV/lucide && echo "synced pkg/vendor/lucide"; }
  for f in fie-i18n.json filerobot-image-editor.min.js; do if [ -f $S/vendor/nox-x/filerobot/$f ] && [ -d $PV/nox-x/filerobot ] && ! cmp -s $S/vendor/nox-x/filerobot/$f $PV/nox-x/filerobot/$f; then mkdir -p $BK/vendor_filerobot; [ -f $PV/nox-x/filerobot/$f ] && cp -p $PV/nox-x/filerobot/$f $BK/vendor_filerobot/; cp -p $S/vendor/nox-x/filerobot/$f $PV/nox-x/filerobot/$f; n=$((n+1)); fi; done
else echo "нет $PV"; fi
echo "WEBROOT_SYNC: обновлено $n файлов, бэкап $BK ($(ls $BK | wc -l) шт.)"
