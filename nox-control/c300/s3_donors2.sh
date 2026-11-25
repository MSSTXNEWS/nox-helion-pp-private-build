#!/bin/bash
# Скачивает F-модули доноров в /workspace/nox/web/build/node_modules (без сборки страниц).
set -e
export PATH=/workspace/nox/tools/node/bin:$PATH
mkdir -p /workspace/nox/web/build && cd /workspace/nox/web/build
[ -f package.json ] || npm init -y >/dev/null
df -BG /workspace | tail -1
npm i --legacy-peer-deps --no-audit --no-fund three postprocessing @tsparticles/slim gsap motion @shoelace-style/shoelace @arwes/frames @arwes/animated @rive-app/canvas lottie-web ninja-keys sortablejs gridstack deep-chat @xyflow/react highlight.js vidstack wavesurfer.js masonry-layout @ffmpeg/ffmpeg fabric phaser boardgame.io chessground grapesjs @blocknote/core ts-fsrs circuitsvis @cosmos.gl/graph cytoscape sigma @theatre/core @jsonforms/core lightweight-charts @mediapipe/tasks-vision mermaid katex 2>&1 | tail -3
du -sh node_modules; df -BG /workspace | tail -1
echo "- $(date +%F) S3: fetch_frontend_donors.sh выполнен (см. du выше)" >> /workspace/nox/PROGRESS.md
