cd /workspace/nox/web/site
grep -l "lv-tag" *.js | head; for f in $(grep -l "lv-tag" *.js | head -2); do echo "OUT: == $f"; grep -o ".\{160\}lv-tag.\{260\}" $f | head -4; grep -o ".\{100\}sl-select.\{250\}" $f | head -3; done
