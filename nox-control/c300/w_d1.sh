echo "C300: w_d1"
for p in 8104 8811 8812 8151 8152 8200; do for u in /slots /running /metrics; do echo -n "$p$u "; curl -s -m4 -w ' [%{http_code}]' http://127.0.0.1:$p$u | head -c 220 | tr '\n' ' '; echo; done; done
echo "== upstream training"; curl -s -m6 -w ' [%{http_code}]' http://127.0.0.1:18091/api/nox/training/status | head -c 900; echo
