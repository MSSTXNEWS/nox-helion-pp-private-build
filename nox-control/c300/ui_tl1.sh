echo "C300: ui_tl1"
export PATH=/workspace/nox/tools/node/bin:$PATH; export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
node -v; npm -v; ls /workspace/nox/tools/node/lib/node_modules 2>&1 | head; ls /workspace/nox/node_modules 2>/dev/null | grep -iE "lighthouse|axe|playwright" | head
ls /workspace/nox/web/site/vendor | grep -iE "axe|lighthouse"; /workspace/nox/venv/bin/pip list 2>/dev/null | grep -iE "axe|playwright|lighthouse"
ls $PLAYWRIGHT_BROWSERS_PATH | head; nproc; free -g | head -2
mkdir -p /tmp/uitl && cd /tmp/uitl && timeout 100 npm view axe-core version 2>&1 | tail -2; timeout 60 npm view lighthouse version 2>&1 | tail -2
