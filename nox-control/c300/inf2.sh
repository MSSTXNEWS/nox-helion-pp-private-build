#!/bin/bash
grep -nE "gateway|8082|NOX_UPSTREAM|CONNECT_TIMEOUT|EMBED_URL|NOX_MODEL|web_server|start_glm|8081" /root/nox/boot_s1.sh | cut -c1-220
echo ==; grep -n "function dot\|dot *=" /root/nox/web/nox_mode.js | cut -c1-250
grep -rn "GLM-5.3\b\|GLM-5\.3 " /root/nox/web/*.js /root/nox/web/chat.html 2>/dev/null | grep -v Flash | cut -c1-160 | head
grep -n "glm_busy" /root/nox/web_server.py | head -3 | cut -c1-200
