S=/workspace/nox/web/site
sed -n 6,26p $S/nox-minichat.js | cut -c1-420
echo ==css; grep -n "nmc" $S/*.css | head -3 | cut -c1-200
grep -c "nxm" $S/*.css | grep -v ":0"
