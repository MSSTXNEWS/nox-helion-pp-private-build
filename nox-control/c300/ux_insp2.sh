echo "C300: ux_insp2"
Q=/workspace/nox/qa_audit.py; S=/workspace/nox/web/site
sed -n 20,38p $Q | cut -c1-330; echo ----; sed -n 120,150p $Q | cut -c1-300
echo == planets; ls $S/vendor/nox-planets
echo == net; for u in https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/machine_shop_01_1k.hdr https://ambientcg.com/get?file=Metal012_1K-JPG.zip; do curl -sIL -m 15 "$u" | head -1; done
echo == registry probe; grep -n "fetch\|HEAD" $S/nox-registry.js | head -5 | cut -c1-200
