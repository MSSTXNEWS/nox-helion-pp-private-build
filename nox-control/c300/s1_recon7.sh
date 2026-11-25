S=/workspace/nox/web/site
cd $S
grep -n "^:root\|--tb-h\|--dock-h\|--colw\|\.stage\|\.feed\|\.col\b\|\.col{\|\.hero\|\.msgs\|\.m\b\|\.m\.\|\.m{\|\.lab\|\.bubble\|\.acts\|\.txt\|\.dock\|\.ctb\|\.composer\|\.row\b\|\.send\|\.seg\b\|\.seg>\|\.tools\|\.hint\|#input\|\.nox-first\|\.think\|\.via\|\.meta\|\.edge\|\.mono\|#app\|\.bar\b\|@media" nox-wow.css | cut -c1-330
echo ==FIRST; sed -n 478,500p nox-wow.js | cut -c1-1500
echo ==THEME; cat nox-theme.js | head -c 700
echo ==NOXCHATUI; cat vendor/nox-chat-ui/nui.css | head -c 2500
echo ==UNIFY; grep -n "#app\|body\|\.stage\|main" nox-unify.css | cut -c1-240 | head -30
