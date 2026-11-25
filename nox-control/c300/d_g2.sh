echo "C300: d_g2"
L=/workspace/nox/web/build/extra.log
grep -E "NPM_MISSING|NPM_FAILED|FAIL|fail|нет " $L | cut -c1-160
grep -c " ok " $L
S=/workspace/nox/web/build/src; V=/workspace/nox/web/site/vendor
mkdir -p $V/talkinghead $V/foliate-js $V/novnc $V/drawio $V/earth
cp -rn $S/TalkingHead/modules $S/TalkingHead/avatars $S/TalkingHead/LICENSE $V/talkinghead/ 2>&1 | tail -1
cp -rn $S/foliate-js/*.js $S/foliate-js/LICENSE $S/foliate-js/vendor $V/foliate-js/ 2>&1|tail -1
cp -rn $S/noVNC/core $S/noVNC/vendor $S/noVNC/app $S/noVNC/vnc_lite.html $S/noVNC/vnc.html $S/noVNC/LICENSE.txt $V/novnc/ 2>&1|tail -1
cp -rn $S/drawio/src/main/webapp/. $V/drawio/ 2>&1|tail -1; cp -n $S/drawio/LICENSE $V/drawio/ 2>/dev/null; find $V/drawio -name "*.map" -delete 2>/dev/null
cp -rn $S/earth/public/. $V/earth/ 2>&1|tail -1; cp -n $S/earth/LICENSE.md $V/earth/
du -sh $V/talkinghead $V/foliate-js $V/novnc $V/drawio $V/earth; ls $V/foliate-js | head -5; cat $S/TalkingHead/package.json | grep -E '"version"|license'
# jupyterlite
cd /workspace/nox/web/build && python3 -m venv jl_venv >/dev/null 2>&1 && ./jl_venv/bin/pip -q install jupyterlite-core jupyterlite-pyodide-kernel 2>&1 | tail -2
mkdir -p jl_work && cd jl_work && timeout 200 ../jl_venv/bin/jupyter lite build --output-dir /workspace/nox/web/build/jl_out 2>&1 | tail -4
du -sh /workspace/nox/web/build/jl_out
df -BG /workspace|tail -1
