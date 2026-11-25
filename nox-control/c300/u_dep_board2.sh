echo "C300: u_dep_board2"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/u_board/nox-u-board.js -o /tmp/nox-u-board.js && node --check /tmp/nox-u-board.js && cp /tmp/nox-u-board.js nox-u-board.js && echo copied || { echo FAIL_FETCH; exit 0; }
sed -i "s#nox-u-board.js?v=u1#nox-u-board.js?v=u2#" chat.html; grep -c "u-board.js?v=u2" chat.html; echo done
