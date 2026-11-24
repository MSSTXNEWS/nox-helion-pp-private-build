S=/workspace/nox/web/site; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/assets; T=$(date +%s)
for f in nox-minichat.js nox-minichat.css; do curl -fsSL "$RAW/$f?t=$T" -o $S/$f; done
cd $S; n=0; for f in *.html; do [ "$f" = chat.html ] && continue; grep -q nox-minichat.js "$f" || { sed -i 's#</body>#<script src="./nox-minichat.js" defer></script>\n</body>#' "$f"; n=$((n+1)); }; done; echo tagged $n
