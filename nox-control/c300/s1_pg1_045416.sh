cd /workspace/nox/web/site
for p in voice atlas map pdf docs documents assistant; do [ -f $p.html ] && echo "== $p $(wc -c < $p.html)"; done
ls *.html | tr '\n' ' ' | head -c 2500; echo
echo ==VOICE; sed -n '/<body/,$p' voice.html | cut -c1-260 | head -60
echo ==VENDORS; ls vendor | tr '\n' ' '; ls vendor/nox-x vendor/nox-lib | tr '\n' ' '
ls vendor/*/ -d | grep -i "globe\|maplibre\|pdf\|monaco\|xterm"
find vendor -maxdepth 3 -iname "*globe*" -o -maxdepth 3 -iname "*pdf*" -o -maxdepth 3 -iname "*monaco*" -o -maxdepth 3 -iname "*xterm*" -o -maxdepth 3 -iname "*maplibre*" | head -20
