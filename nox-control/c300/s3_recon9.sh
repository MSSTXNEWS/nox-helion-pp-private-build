#!/bin/bash
S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server
echo "#### svc_registry.json"; head -c 2500 $P/svc_registry.json
echo; echo "#### vendor ls"; ls $S/vendor | tr '\n' ' '
echo; echo "#### tasks-vision/nosleep/cmdk"; ls $S/vendor/tasks-vision $S/vendor/mediapipe* $S/vendor/nosleep* $S/vendor/cmdk 2>&1 | head -30
echo "#### hand model?"; find /workspace/nox -maxdepth 6 \( -name "hand_landmarker*" -o -name "gesture_recognizer*" \) 2>/dev/null | head -3
echo "#### svc scripts"; ls /workspace/nox/svc 2>/dev/null | head -20; ls /workspace/nox/svc/*.sh 2>/dev/null | head
echo "#### nox_cmd handle excerpt"; sed -n 44,64p $P/nox_cmd.py
