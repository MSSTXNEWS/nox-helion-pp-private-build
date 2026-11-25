echo "C300: d_tex0"
for u in https://www.solarsystemscope.com/textures/download/2k_earth_daymap.jpg https://www.solarsystemscope.com/textures/download/8k_earth_daymap.jpg https://www.solarsystemscope.com/textures/ https://www.solarsystemscope.com/textures/download/2k_saturn_ring_alpha.png https://upload.wikimedia.org/wikipedia/commons/2/2c/Solarsystemscope_texture_8k_earth_daymap.jpg; do
 echo "== $u"; curl -sL -m 30 -A "Mozilla/5.0" -o /tmp/t.bin -w "%{http_code} %{content_type} %{size_download}\n" "$u"; file /tmp/t.bin | cut -c1-120
done
