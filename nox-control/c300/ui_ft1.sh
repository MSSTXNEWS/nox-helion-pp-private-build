echo "C300: ui_ft1"
S=/workspace/nox/web/site; V=/workspace/nox/web/v29src
find $V /workspace/nox/web/pkg /workspace/nox/web/build -iname "tektur*" 2>/dev/null | head -8
find $V /workspace/nox/web/pkg -iname "orbitron*latin-700*" 2>/dev/null | head -3
ls $S/vendor/fonts | head; ls $S/vendor/fonts-wow | head -5
grep -rho "url([^)]*tektur[^)]*)" $S/*.css 2>/dev/null | sort -u | head -3; grep -ln "tektur-latin" $S/*.css $S/vendor/fonts*/*.css 2>/dev/null | head
