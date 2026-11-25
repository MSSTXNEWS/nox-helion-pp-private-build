#!/bin/bash
echo "C300: p2_img_ctx"; S=/workspace/nox/web/pkg/server; N=/workspace/nox
echo "## web_server 90-130"; sed -n 90,130p $S/web_server.py | cut -c1-200
echo "## web_server 303-345"; sed -n 303,345p $S/web_server.py | cut -c1-200
echo "## imgsvc API"; curl -s -m 5 http://127.0.0.1:8500/openapi.json | head -c 1500; echo
echo "## imgsvc source"; f=$(ls $N/ops/imgsvc*/*.py $N/svc/imgsvc*/*.py $N/imgsvc*/*.py 2>/dev/null | head -3); echo "$f"; grep -n 'POST\|/generate\|/health\|/file\|"prompt"\|width\|steps\|path' $(echo $f | cut -d' ' -f1) 2>/dev/null | cut -c1-180 | head -40
echo "## previous draw usage hints"; grep -rn 'draw_request\|photo_request\|local_generate' $N/ops/controller/gen_draw_sft_lite.py $N/ops/controller/PLAN_A.md $N/ops/controller/PROGRESS.md 2>/dev/null | cut -c1-220 | head -12
echo "## images dir"; ls -t $N/images 2>/dev/null | head -3
echo "## DONE"
