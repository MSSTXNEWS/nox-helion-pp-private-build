echo "C300: ui_sc3"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; export PATH=/workspace/nox/tools/node/bin:$PATH
T=/workspace/nox/tools/uiscore; PY=/workspace/nox/venv/bin/python
CP=$(ls /workspace/nox/tools/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1); echo CP=$CP; ls /workspace/nox/tools/ms-playwright | head
timeout 100 $T/node_modules/.bin/lighthouse http://127.0.0.1:8091/web/system.html --only-categories=accessibility --output=json --output-path=/tmp/lhp.json --quiet --chrome-flags="--headless --no-sandbox --disable-gpu" --chrome-path=$CP 2>&1 | head -12 | cut -c1-300
ls -la /tmp/lhp.json 2>&1
