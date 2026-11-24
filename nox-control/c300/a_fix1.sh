S=/workspace/nox/web/site/vendor/llm-viz
grep -rl "native.wasm" $S --include=*.js | head
find /workspace/nox/build_a/llm-viz -name native.wasm -not -path "*/node_modules/*" | head -3
for f in $(grep -rl "/native.wasm" $S --include=*.js); do cp -n $f $f.bak_a_1; sed -i 's|"/native.wasm"|"/web/vendor/llm-viz/native.wasm"|g' $f; done
ls $S/native.wasm; curl -s -o /dev/null -w '%{http_code}\n' 127.0.0.1:8091/web/vendor/llm-viz/native.wasm
grep -rho ".\{30\}native.wasm.\{20\}" $S --include=*.js | head -3
