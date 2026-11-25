# Скачивает F-модули доноров в /workspace/nox/web/build/node_modules (+ git-доноры в build/src). Без сборки страниц.
export PATH=/workspace/nox/tools/node/bin:$PATH
mkdir -p /workspace/nox/web/build/src && cd /workspace/nox/web/build
[ -f package.json ] || npm init -y >/dev/null
df -BG /workspace | tail -1
PK="three postprocessing @tsparticles/slim @tsparticles/engine gsap motion @shoelace-style/shoelace @arwes/frames @arwes/animated @rive-app/canvas lottie-web ninja-keys cmdk sortablejs gridstack @tremor/react @assistant-ui/react deep-chat @xyflow/react @ag-ui/client highlight.js vidstack @vidstack/react swiper shaka-player dashjs wavesurfer.js masonry-layout @mozilla/readability @ffmpeg/ffmpeg @ffmpeg/util @ffmpeg/core fabric phaser boardgame.io chessground grapesjs @blocknote/core ts-fsrs circuitsvis @cosmos.gl/graph cytoscape sigma graphology @theatre/core @theatre/studio @jsonforms/core @pixiv/three-vrm @mediapipe/tasks-vision @huggingface/transformers mermaid katex lightweight-charts echarts 3d-force-graph globe.gl maplibre-gl @excalidraw/excalidraw yjs @fullcalendar/core frappe-gantt monaco-editor @xterm/xterm tesseract.js pdfjs-dist pdf-lib react react-dom esbuild"
OK=""; for p in $PK; do v=$(npm view "$p" version 2>/dev/null); if [ -n "$v" ]; then OK="$OK $p"; else echo "NPM_MISSING $p"; fi; done
echo "NPM_OK: $OK"
npm i --legacy-peer-deps --no-audit --no-fund $OK 2>&1 | tail -5
for p in $OK; do [ -d node_modules/$p ] || { echo "RETRY $p"; npm i --legacy-peer-deps --no-audit --no-fund $p 2>&1 | tail -2; }; done
for p in $OK; do [ -d node_modules/$p ] || echo "NPM_FAILED $p"; done
# git-доноры: имя репозиторий
S=/workspace/nox/web/build/src
for e in TalkingHead=met4citizen/TalkingHead stellarium-web-engine=Stellarium/stellarium-web-engine earth=cambecc/earth foliate-js=johnfactotum/foliate-js noVNC=novnc/noVNC ai-elements=vercel/ai-elements omniclip=omni-media/omniclip feishin=jeffvli/feishin; do
  n=${e%%=*}; r=${e#*=}
  [ -d $S/$n/.git ] || timeout 600 git clone --depth 1 https://github.com/$r.git $S/$n 2>&1 | tail -1
  [ -d $S/$n ] && echo "GIT_OK $n" || echo "GIT_FAILED $n"
done
# drawio: только webapp (sparse)
if [ ! -d $S/drawio ]; then git clone --depth 1 --filter=blob:none --sparse https://github.com/jgraph/drawio.git $S/drawio 2>&1 | tail -1; (cd $S/drawio && git sparse-checkout set src/main/webapp 2>&1 | tail -1); fi
[ -d $S/drawio/src/main/webapp ] && echo "GIT_OK drawio" || echo "GIT_FAILED drawio"
du -sh node_modules $S; df -BG /workspace | tail -1
echo FETCHDONE
