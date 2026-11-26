# th_ensure: идемпотентно (пере)применить тему «Графит». Вызов: bash ensure.sh [force]. Маркер: в nox-theme.js строка data-nox-theme=graphite/graphite и файл nox-graphite.css.
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
ok(){ grep -q "graphite" nox-theme.js 2>/dev/null && [ -s nox-graphite.css ] && [ -s nox-graphite-map.css ] && grep -q "TH-GRAPHITE" nox-wow-bg.js && grep -q "NOXiconUrl" nox-nav.js && [ -s nox-motion.js ] && [ -d vendor/lucide/icons ]; }

synchro(){ curl -fsSL --retry 5 https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh -o /tmp/webroot_sync.sh && bash /tmp/webroot_sync.sh; }
if [ "$1" != force ] && ok; then echo "TH_MARKER_OK"; synchro; exit 0; fi
echo "TH_REAPPLY"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite
G=/tmp/th_ens; rm -rf $G; mkdir -p $G
for f in nox-graphite.css nox-theme.js nox-motion.css nox-motion.js nox-th-fix.css nox-icons.js nox-logo.svg fie-i18n.json lucide.zip patch.py th_gen_map.py; do curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/$f -o $G/$f && [ -s $G/$f ] || { echo "FAIL fetch $f"; exit 1; }; done
node --check $G/nox-theme.js && node --check $G/nox-icons.js && node --check $G/nox-motion.js || { echo FAIL_SYNTAX; exit 1; }
BK=/workspace/nox/web/th_ens_bak_$TS; mkdir -p $BK; cp nox-*.js nox-*.css live.html $BK/ 2>/dev/null
cp $G/nox-graphite.css $G/nox-theme.js $G/nox-motion.css $G/nox-motion.js $G/nox-th-fix.css $G/nox-icons.js $G/nox-logo.svg .
[ -d vendor/lucide/icons ] || { mkdir -p vendor/lucide && $PY -c "import zipfile;zipfile.ZipFile('$G/lucide.zip').extractall('vendor/lucide')"; }
mkdir -p vendor/nox-x/filerobot; cp $G/fie-i18n.json vendor/nox-x/filerobot/
$PY $G/patch.py $S | grep -v "^already" | tr '\n' ';'; echo
$PY $G/th_gen_map.py $S $S/nox-graphite-map.css
if ok; then echo "TH_REAPPLY_OK"; else echo "TH_REAPPLY_INCOMPLETE"; for c in "grep -q graphite nox-theme.js" "grep -q TH-GRAPHITE nox-wow-bg.js" "grep -q NOXiconUrl nox-nav.js" "[ -s nox-graphite-map.css ]"; do eval "$c" && echo "  ok: $c" || echo "  MISSING: $c"; done; fi
synchro
