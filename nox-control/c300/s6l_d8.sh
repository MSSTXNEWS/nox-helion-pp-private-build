echo "K1: s6l_d8"
N=/workspace/nox; D=$N/ops/dpo
echo "open_proc=$(pgrep -f s6_open.py | wc -l) now=$(date -u +%H:%M)"; ls -la $D/pers1_open* 2>/dev/null | awk '{print $5,$9}'; tail -c 600 $D/s6_open.log
if [ "$(pgrep -f s6_open.py | wc -l)" = 0 ]; then python3 -I $D/s6_assemble.py 2>&1 | tail -4; cat $D/pers1_open_manifest.json 2>/dev/null; fi
echo END
