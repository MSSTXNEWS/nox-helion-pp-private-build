J=/workspace/nox/web/build/node_modules/three/examples/jsm; ls $J | head -3; du -sh $J
cp -rn $J/. /workspace/nox/web/site/vendor/three/addons/ ; ls /workspace/nox/web/site/vendor/three/addons | head -4
grep -n "setDecoderPath\|gstatic" /workspace/nox/web/site/vendor/talkinghead/modules/talkinghead.mjs | head -3
df -h /workspace | tail -1
cd /tmp; sed -i "s#await pg.wait_for_timeout(8000)#await pg.wait_for_timeout(30000)#" /tmp/th3.py; /workspace/nox/venv/bin/python /tmp/th3.py 2>&1
