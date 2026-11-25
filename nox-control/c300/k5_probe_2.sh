echo "C300: k5_probe_2"
S=/workspace/nox/web/site; cd $S
for v in fabric pixi howler typewriter embla confetti vidstack transformers mediapipe codemirror rive merge; do echo "-- $v"; ls -d vendor/*$v* vendor/nox-x/*$v* vendor/nox-wow/*$v* vendor/nox-extra/*$v* 2>/dev/null | head -6; done
for d in vendor/howler* vendor/*embla* vendor/canvas-confetti vendor/*fabric* vendor/*typewriter* vendor/*rive* vendor/*mediapipe* vendor/*codemirror*; do echo "## $d"; ls $d | head -8; done
cat nox-k4-inbox.js | head -12 | cut -c1-200
echo; sed -n 1,25p nox-k3-core.js | cut -c1-300
head -c 1500 studio.html; echo; sed -n 1,200p photo.html | grep -E 'ps-ed|fie|<img|canvas' | head -8 | cut -c1-250
grep -E 'id="(mAud|mLst|mu)"|<h1' music.html | cut -c1-200 | head; grep -n 'cnLive\|<video' cinema.html | cut -c1-200 | head -5
grep -c '' /tmp/k2_qa.py; ls /workspace/nox/web/site/vendor/nox-wow | head -40 | tr '\n' ' '
