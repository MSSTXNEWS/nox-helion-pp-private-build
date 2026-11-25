D=/workspace/nox/web/site/vendor/planets; mkdir -p $D/2k $D/8k; cd $D
U=https://www.solarsystemscope.com/textures/download
for r in 2k 8k; do for n in sun mercury venus_surface venus_atmosphere earth_daymap earth_nightmap earth_clouds earth_normal_map earth_specular_map moon mars jupiter saturn saturn_ring_alpha uranus neptune stars_milky_way ceres eris haumea makemake; do
 f=${r}_$n; ext=jpg; [ $n = saturn_ring_alpha ] && ext=png
 [ -s $r/$f.$ext ] && continue
 c=$(curl -sL -m 120 -A "Mozilla/5.0" -o /tmp/dtex.$$ -w "%{http_code}" $U/$f.$ext)
 if [ "$c" = 200 ] && file /tmp/dtex.$$ | grep -qi image; then mv /tmp/dtex.$$ $r/$f.$ext; else echo "MISS $f $c"; fi
done; done
rm -f /tmp/dtex.$$
cat > LICENSE <<'L'
Planet textures: Solar System Scope (https://www.solarsystemscope.com/textures/)
Author: Solar System Scope / INOVE, based on NASA elevation and imagery data.
License: Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/
Required attribution: "Textures by Solar System Scope (solarsystemscope.com), CC BY 4.0".
You may share and adapt, including commercially, provided attribution is given.
L
cp LICENSE ATTRIBUTION.txt
ls 2k | wc -l; ls 8k | wc -l; du -sh $D; ls 8k; df -BG /workspace | tail -1
