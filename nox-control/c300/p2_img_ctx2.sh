#!/bin/bash
echo "C300: p2_img_ctx2"; F=/workspace/nox/imgsvc/image_service.py
grep -n 'def do_POST\|/generate\|body\.get\|req\.get\|data\.get\|payload\.get\|"path"\|"url"\|"ok"\|"seed"\|"width"\|"height"\|"steps"\|"model"\|"prompt"\|"negative' $F | cut -c1-190 | head -60
echo "## last json meta"; cat /workspace/nox/images/$(ls -t /workspace/nox/images | grep json | head -1) | head -c 700; echo
echo "## sun_adapter generate"; grep -n '/generate\|"path"\|"url"\|body.get\|req.get' /workspace/nox/ops/sun_adapter/sun_adapter.py | cut -c1-190 | head -25
echo "## DONE"
