echo S4RUN:s6_recon1
cd /workspace/nox/web/site
for p in photo news cinema music studio creative board tv; do echo "== $p"; cat qa/rework/$p.json | head -c 1500; echo; ls qa/rework | grep "^$p\." ; done
echo; wc -c photo.html news.html nox-s2-photo.css nox-s2-photo.js nox-s2-news.js nox-s2.css nox-s4-sl.js
echo; cat nox-s4-sl.js | head -c 3500
echo; grep -o '<link[^>]*>\|<script[^>]*src[^>]*>' photo.html
