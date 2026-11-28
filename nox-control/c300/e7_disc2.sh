echo "K1: e7_disc2 (read-only)"; N=/workspace/nox
F=$N/imgsvc/image_service.py; grep -n -E "/generate|json\.loads|\.get\(\"(prompt|width|height|steps|size)|def |send_response|wfile|b64|path" $F | head -40 | cut -c1-220
echo "## api_bridge brief"; grep -n "morning_brief_v5" $N/ops/api_bridge/api_bridge.py | head -5 | cut -c1-260
echo "## gates"; ls -t $N/state/gates 2>/dev/null | head -3; find $N/state $N/agent -maxdepth 3 -name '*gate*' -newer $N/state/core/passport.json 2>/dev/null | head -8; find $N -maxdepth 4 -name 'gate_log*' 2>/dev/null | head -3
echo "## voice 8400"; curl -s -m 5 http://127.0.0.1:8400/health | head -c 200; echo
echo "## mods dir"; ls $N/mods | tr '\n' ' '; echo
echo "## sup weekly"; supervisorctl status nox_weekly_exam 2>&1 | head -2
echo "## last exam"; python3 -I -c "import json;d=json.load(open('$N/state/core/weekly_exam.json'));print(d['ts'],d['score'])"
echo "## qa conv filter"; ls $N/state/web/web_conv | head -3; ls $N/state/web/web_conv | wc -l
echo "## promises"; head -c 300 $N/state/core/promises.json; echo
echo END
