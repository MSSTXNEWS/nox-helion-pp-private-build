echo "C300: d_b2"
B=/workspace/nox/web/build; export PATH=/workspace/nox/tools/node/bin:$PATH
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL $R/d_build_vendor.mjs -o $B/d_build_vendor.mjs; curl -fsSL $R/IDEAS.md -o $B/IDEAS.md
cd $B
# пакеты из реестра: первая колонка таблицы после заголовка реестра
sed -n '/^## Реестр пакетов/,$p' IDEAS.md | grep -E '^\| [@a-z0-9]' | grep -v 'Пакет' | awk -F'|' '{gsub(/ /,"",$2);print $2}' | grep -v '^---' > extra_pkgs.txt
PRI="cmdk butterchurn 3d-force-graph @paper-design/shaders nosleep.js tone globe.gl cobe page-flip"
(for p in $PRI; do echo $p; done; cat extra_pkgs.txt) | awk '!s[$0]++' > extra_all.txt
wc -l extra_all.txt
cat > extra.sh <<'X'
export PATH=/workspace/nox/tools/node/bin:$PATH; cd /workspace/nox/web/build
OK=""; for p in $(cat extra_all.txt); do [ -d node_modules/$p ] && continue; v=$(npm view "$p" version 2>/dev/null); [ -n "$v" ] && OK="$OK $p" || echo "NPM_MISSING $p"; done
npm i --legacy-peer-deps --no-audit --no-fund $OK 2>&1 | tail -3
for p in $OK; do [ -d node_modules/$p ] || { npm i --legacy-peer-deps --no-audit --no-fund $p 2>&1 | tail -1; [ -d node_modules/$p ] || echo "NPM_FAILED $p"; }; done
echo INSTDONE; df -BG /workspace|tail -1
EXTRA=extra_all.txt node d_build_vendor.mjs
echo ALLDONE
X
nohup setsid bash extra.sh > extra.log 2>&1 &
sleep 2; echo started
