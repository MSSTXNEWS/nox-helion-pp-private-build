echo "C300: ch_dc21"
V=/workspace/nox/web/v29src
for f in $(grep -rIl -i "liquid" $V/V29_3_FROZEN/site $V/FASTWOW 2>/dev/null | grep -v "\.md$\|MANIFEST" | head -8); do echo "## $f $(wc -c <$f)"; grep -n -i -o ".\{0,90\}liquid.\{0,160\}" $f | head -5 | cut -c1-300; done
echo "== glass-ish css"; grep -rIn -i -o "\.[a-z-]*glass[a-z-]*{[^}]\{0,220\}}" $V/V29_3_FROZEN/site --include=*.css | head -8 | cut -c1-360
