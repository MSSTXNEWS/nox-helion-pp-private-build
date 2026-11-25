echo S4RUN:s6_recon5
cd /workspace/nox/web/site
grep -n "cn-" nox-s2.css | cut -c1-230 | head -60
echo "## js render"; grep -o "class=\"cn-[a-z0-9 -]*\"" nox-s2-cinema.js | sort | uniq -c | sort -rn | head -30
grep -n "Swiper\|swiper" nox-s2-cinema.js | head -5 | cut -c1-200
echo "## chips"; grep -o "s2-chip[^\"']*" nox-s2-cinema.js | sort | uniq -c | head
