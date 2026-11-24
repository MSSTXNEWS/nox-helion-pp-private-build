S=/workspace/nox/web/site
echo "=== consciousness.html"; sed -n 17,24p $S/consciousness.html
echo "=== p-brain"; wc -c $S/nox-p-brain.js; cat $S/nox-p-brain.js | cut -c1-600
echo "=== training.html body"; sed -n 19,33p $S/training.html
echo "=== p-training"; wc -c $S/nox-p-training.js; cat $S/nox-p-training.js | cut -c1-500 | head -60
echo "=== wow.js 100-200"; sed -n 100,200p $S/nox-wow.js | cut -c1-330
