S=/workspace/nox/web/site; curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/assets/nox-minichat.css?t=$(date +%s)" -o $S/nox-minichat.css
grep -n "ERROR\|error\|No space\|Could not" /workspace/nox/invoke_install.log | head -8 | cut -c1-300
du -sh /workspace/nox/invoke; df -h /workspace | tail -1
