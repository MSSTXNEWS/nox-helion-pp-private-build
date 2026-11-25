S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site/qa/rework; ls atlas.fixed 2>&1; [ -e atlas.fixed ] || echo "S1: atlas — вкладки Глобус/Карта на sl-tab-group.at-tg, слои sl-switch, легенда, поиск; e2e 11/11 без мёртвых (1440, 390)." > atlas.fixed; ls atlas.fixed
