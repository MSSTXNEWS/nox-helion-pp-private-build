S=/workspace/nox/web/site
[ -f $S/studio.html.bak_atelier_20261124 ] || cp $S/studio.html $S/studio.html.bak_atelier_20261124
curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/assets/studio.html?t=$(date +%s)" -o $S/studio.html
