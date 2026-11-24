curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/qa_audit.py?a2" -o /tmp/qa_new.py && python3 -m py_compile /tmp/qa_new.py && cp /tmp/qa_new.py /workspace/nox/qa_audit.py && echo audit deployed
cd /workspace/nox/build_a
for p in react @xyflow/react @assistant-ui/react deep-chat 3d-force-graph three @arwes/frames @arwes/animated @arwes/bgs echarts @cosmos.gl/graph esbuild; do
 echo "$p $(node -p "const j=require('./node_modules/$p/package.json');j.version+' '+(j.license||JSON.stringify(j.licenses))" 2>/dev/null || python3 -c "import json;j=json.load(open('node_modules/$p/package.json'));print(j['version'],j.get('license'))")"; ls node_modules/$p | grep -i licen | head -2; done
echo --- llm-viz; ls llm-viz; head -5 llm-viz/LICENSE*; grep -E '"(name|build|dev|next)"' llm-viz/package.json | head; du -sh llm-viz
echo --- arwes; ls node_modules/@arwes/frames/build 2>/dev/null | head; cat node_modules/@arwes/frames/package.json | grep -E '"(main|module|version)"'
echo --- assistant-ui exports; ls node_modules/@assistant-ui/react/dist | head -20
