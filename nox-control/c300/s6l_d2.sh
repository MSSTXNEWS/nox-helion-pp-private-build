echo "K1: s6l_d2"
N=/workspace/nox; D=$N/ops/dpo; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
curl -fsSL --retry 3 $RAW/s6l_files/s6_assemble.py -o $D/s6_assemble.py
echo "open_proc=$(pgrep -f s6_open.py | wc -l)"; tail -c 700 $D/s6_open.log; ls -la $D/pers1_open.jsonl 2>/dev/null | awk '{print $5}'
python3 -I $D/s6_assemble.py 2>&1 | tail -6
echo END
