echo "C300: d_g4"
B=/workspace/nox/web/build; export PATH=/workspace/nox/tools/node/bin:$PATH; cd $B
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL $R/d_build_vendor.mjs -o d_build_vendor.mjs
for a in animated frames; do (cd node_modules/@arwes/$a && npm i motion@10.18.0 --no-save --no-audit --no-fund --legacy-peer-deps 2>&1 | tail -1); done
npm i --legacy-peer-deps --no-audit --no-fund @preact/signals preact moment vis-data vis-util component-emitter xss hammerjs propagating-hammerjs uuid keycharm @rjsf/utils @rjsf/validator-ajv8 2>&1 | tail -1
node -e "const p=require('./node_modules/@cosmos.gl/graph/package.json');console.log(JSON.stringify({d:p.dependencies,p:p.peerDependencies}))"
CP=$(node -e "const p=require('./node_modules/@cosmos.gl/graph/package.json');const o=Object.assign({},p.dependencies,p.peerDependencies);console.log(Object.entries(o).filter(([k])=>!/^(react|react-dom)$/.test(k)).map(([k,v])=>k+'@'+v).join(' '))")
npm i --legacy-peer-deps --no-audit --no-fund $CP 2>&1 | tail -1
ls node_modules/circuitsvis/dist | head
EXTRA=extra_all.txt node d_build_vendor.mjs arwes-frames,arwes-animated,circuitsvis,cosmos-gl,schedule-x-calendar,vis-timeline,rjsf-core,maplibre-gl,blocknote 2>&1 | tail -25
