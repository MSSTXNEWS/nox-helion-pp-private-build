N=/workspace/nox; RAW="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF}/nox-control/c300/s4w2_files"
echo "S4ISO $(date +%F_%H:%M)"
curl -fsSL --retry 3 "$RAW/iso_test.py" -o $N/mods/iso_test.py && python3 -I $N/mods/iso_test.py
