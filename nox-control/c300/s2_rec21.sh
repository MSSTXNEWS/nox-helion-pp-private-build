#!/bin/bash
X=/workspace/nox/web/site/vendor/nox-x
find $X/excalidraw/dist -maxdepth 2 | head -20; ls -la $X/excalidraw/dist/*.js 2>/dev/null | head -5
ls -la /workspace/nox/web/site/vendor/excalidraw-excalidraw | head
head -c 400 $X/excalidraw/dist/excalidraw.production.min.js 2>/dev/null; echo
