echo S4RUN:s6_recon2
cd /workspace/nox/web/site
echo "#### photo.html"; sed 's/<style[^>]*>.*<\/style>//' photo.html | head -c 6000
echo; echo "#### s4-sl"; head -c 3000 nox-s4-sl.js
echo; echo "#### sizes"; wc -c photo.html news.html cinema.html music.html studio.html creative.html board.html tv.html nox-s2-*.js nox-s2*.css nox-s4-sl.js
echo "#### news.html"; head -c 3500 news.html
echo "#### photo.css"; head -c 2500 nox-s2-photo.css
echo "#### shoelace"; ls vendor | grep -i shoe; ls vendor/shoelace 2>/dev/null | head
