echo S4RUN:s6_p17
cd /workspace/nox/web/site
grep -n "cvStyle" nox-s2-music.js | cut -c1-260 | head -12
echo "## sizes"; wc -c nox-settings-tabs.js nox-set-x.js nox-set-search.js nox-s4-training.js nox-tools.js settings.html training.html tools.html 2>&1
for p in settings training tools; do echo "## $p"; grep -o '<script[^>]*src="[^"]*"' $p.html | sed 's/<script[^>]*src=//' | tr '\n' ' '; echo; done
ls vendor | grep -i "xterm\|ninja\|cmdk\|gridstack\|shoelace"
