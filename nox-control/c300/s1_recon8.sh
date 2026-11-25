cd /workspace/nox/web/site
grep -n "function renderThreads" nox-wow.js | cut -c1-1800
grep -n "function autosize\|autosize =" nox-wow.js | cut -c1-400
sed -n '/function holo(th)/,/^  }/p' nox-chat-x.js | cut -c1-900 | head -20
tail -c 1500 nox-chat-x.js
echo ==DOCK; grep -n "dock-h\|--tb-h" nox-dock.js nox-dock-pop.js nox-dock-wow.js nox-unify.css | cut -c1-160 | head
echo ==ICONS; ls vendor | head -80 | tr '\n' ' '
echo; ls vendor/nox-lib 2>/dev/null | tr '\n' ' '
ls /workspace/nox/web/build/node_modules 2>/dev/null | head -50 | tr '\n' ' '
df -h / /workspace | tail -2
