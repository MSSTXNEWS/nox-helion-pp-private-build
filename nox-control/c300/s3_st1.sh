S=/workspace/nox/web/site
echo "== ST1"; wc -c $S/nox-settings-tabs.js $S/nox-planets3d.js $S/nox-mac.css $S/nox-settings-tabs.css
grep -n "dataset.tab\|setActive\|const show\|function show\|aria-selected\|nxs-side\|nox-seen\|querySelectorAll('section" $S/nox-settings-tabs.js | cut -c1-260 | head -20
grep -n "data-tab\|nxs-side\|\.nxs-tabs\|nxs-hide" $S/nox-settings-tabs.css $S/nox-mac.css | cut -c1-220 | head -14
sed -n 36,44p $S/nox-planets3d.js | cut -c1-200; sed -n 50,70p $S/nox-planets3d.js | cut -c1-220
ls /workspace/nox/web/site/vendor/planets/2k | head -3; ls -l $S/vendor/planets/2k/2k_jupiter.jpg; which ffmpeg convert
