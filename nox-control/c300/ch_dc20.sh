echo "C300: ch_dc20"
V=/workspace/nox/web/v29src; ls $V | head; ls $V/V29_3_FROZEN 2>/dev/null | head -20
grep -rIl -i "liquid" $V 2>/dev/null | head -15
echo "== lg css"; for f in $(grep -rIl -i "feDisplacementMap\|liquid-glass\|lg-layer" $V --include=*.css --include=*.js --include=*.html 2>/dev/null | head -4); do echo "## $f $(wc -c <$f)"; grep -n -i "backdrop\|displacement\|lg-layer\|lg-sheen\|specular\|refract" $f | head -14 | cut -c1-260; done
