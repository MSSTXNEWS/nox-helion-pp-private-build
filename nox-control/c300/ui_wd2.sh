echo "C300: ui_wd2"
V=/workspace/nox/web/v29src
for d in V29_3_FROZEN FASTWOW; do echo "=== $d"; ls $V/$d | head -30; done
echo "== world files (FASTWOW)"; cd $V/FASTWOW; grep -rlI "SOMNIUM" . 2>/dev/null | head -30
echo "== world files (FROZEN)"; cd $V/V29_3_FROZEN; grep -rlI "SOMNIUM" . 2>/dev/null | head -20
echo "== palettes/buttons"; cd $V/FASTWOW; grep -rlI "glacier\|amethyst" . 2>/dev/null | head -15
echo "== sizes top js/css"; find $V/FASTWOW $V/V29_3_FROZEN \( -iname "*world*" -o -iname "*theme*" -o -iname "*palette*" -o -iname "*liquid*" \) -type f -size +1k 2>/dev/null | head -40 | xargs ls -la 2>/dev/null | awk '{print $5,$9}'
