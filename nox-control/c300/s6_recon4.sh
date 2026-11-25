echo S4RUN:s6_recon4
cd /workspace/nox/web/site
cat nox-cmd.js | head -c 2500
echo "## chat usage"; grep -o "fetch([^)]*api/chat[^)]*)[^;]\{0,300\}" nox-s2-news.js nox-s2-studio.js | head -4
grep -n "NOXcmd" nox-s2-news.js | head -3 | cut -c1-300
echo "## s4-sl tail"; tail -c 700 nox-s4-sl.js
grep -c "nox-s4-sl" training.html projects.html photo.html
echo "## training buttons"; grep -o '<button[^>]*>' training.html | head -5
ls nox-s4-*.js
echo "## dialog/sl in photo.html tail"; tail -c 1500 photo.html
