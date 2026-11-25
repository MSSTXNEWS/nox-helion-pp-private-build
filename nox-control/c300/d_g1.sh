echo "C300: d_g1"
S=/workspace/nox/web/build/src; V=/workspace/nox/web/site/vendor
for n in TalkingHead stellarium-web-engine earth foliate-js noVNC drawio omniclip; do echo "== $n $(du -sh $S/$n | cut -f1)"; ls $S/$n | head -25 | tr '\n' ' '; echo; done
echo; ls $S/TalkingHead/modules $S/TalkingHead/avatars 2>/dev/null | head -30
ls $S/earth/public | head; ls $S/drawio/src/main/webapp | head -30; du -sh $S/drawio/src/main/webapp
find $S/stellarium-web-engine -name "*.wasm" -o -name "stellarium-web-engine.js" | head
tail -5 /workspace/nox/web/build/extra.log
