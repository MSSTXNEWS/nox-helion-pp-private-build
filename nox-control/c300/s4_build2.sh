N=/workspace/nox; RAW="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF}/nox-control/c300/s4_files"
echo "S4B2 $(date +%F_%H:%M)"
curl -fsSL --retry 3 "$RAW/foreign_mark.py" -o $N/mods/foreign_mark.py && curl -fsSL --retry 3 "$RAW/test_foreign_mark.py" -o $N/mods/tests/test_foreign_mark.py && curl -fsSL --retry 3 "$RAW/build_dpo7_inj2.py" -o $N/ops/dpo/build_dpo7_inj2.py && echo fetched
cd $N/mods && python3 -I -m pytest -q tests 2>&1 | tail -3
python3 -I $N/ops/dpo/build_dpo7_inj2.py 2>&1 | tail -c 3500
ls -la $N/ops/dpo/dpo_inj2_* | awk '{print $5,$9}'
