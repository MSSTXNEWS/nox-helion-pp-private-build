echo "C300: srv_k34"
cd /workspace/nox
F=$(ls distill_v2/code/liska_gates.py agent/liska_gates.py 2>/dev/null | head -1); echo F=$F; wc -l $F
grep -n "^def \|^    def " $F | cut -c1-160 | head -40
awk '/def round_gates/{p=1} p{print; n++} n>70{exit}' $F | cut -c1-210
grep -n "LIVE_TURN" agent/*.py web/*.py ops/*.py 2>/dev/null | head -5 | cut -c1-200
sed -n '2300,2345p' distill_v2/code/distill_v2.py | cut -c1-190
