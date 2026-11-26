echo "C300: srv_k27"
cd /workspace/nox
grep -c loss_weights ops/dpo/train_dpo.py
echo == draw5; tail -n 12 state/p3/draw5.out | cut -c1-250; sed -n '1,25p' state/p3/draw5.py | cut -c1-200
echo == qa; find . -maxdepth 4 -iname "qa-*" -not -path "*/venv/*" 2>/dev/null | head -8; ls state | grep -i qa | head
