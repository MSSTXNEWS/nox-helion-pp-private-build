S=/workspace/nox/web/site
head -c 1800 $S/nox-s6-sl.js; echo; echo ===; grep -ln "shoelace" $S/nox-*.js | head; ls $S/vendor/shoelace $S/vendor/shoelace/cdn | head -30
grep -o "shoelace[^'\"]*autoloader[^'\"]*\|shoelace-autoloader[^'\"]*\|shoelace.js" $S/nox-*.js | sort | uniq -c | head
echo ===; sed -n 1,60p $S/nox-s2.css | cut -c1-200 | head -30
ls $S/vendor/shoelace/cdn/assets/icons | head -3; ls $S/vendor/shoelace/cdn/assets/icons | wc -l
python3 -c "import playwright;print('pw ok')"
