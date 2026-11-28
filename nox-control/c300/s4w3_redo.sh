N=/workspace/nox; RAW="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF}/nox-control/c300/s4w3_files"
echo "S4W3R $(date +%F_%H:%M)"
for f in restore_full stop_test; do curl -fsSL --retry 3 "$RAW/$f.py" -o $N/mods/$f.py || echo "FAIL $f"; done
cd $N/mods && python3 -I -m pytest -q tests/test_restore_full.py tests/test_stop_test.py 2>&1 | tail -1
echo "## restore_full"; python3 -I $N/mods/restore_full.py | cut -c1-2200
supervisorctl restart nox_restore_full 2>&1 | tail -1
echo "## stop_test"; python3 -I $N/mods/stop_test.py --trials 3 | cut -c1-1500
