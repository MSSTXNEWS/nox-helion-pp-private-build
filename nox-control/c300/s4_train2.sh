S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-training.js nox-s4-training.css; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || exit 1; done; grep -c s4wb nox-s4-training.js
