echo "C300: srv_k19"
cd /workspace/nox
find . -maxdepth 4 \( -name "build_kto.py" -o -name "train_kto_s2.py" -o -name "*antisyc*" -o -name "*sycoph*" \) -not -path "*/venv/*" 2>/dev/null | head
for f in $(find . -maxdepth 4 \( -name "build_kto.py" -o -name "train_kto_s2.py" \) -not -path "*/venv/*" | head -2); do echo "=== $f"; wc -l $f; sed -n '1,60p' $f | cut -c1-200; done
ls distill_v2/ckpt_keep | head; ls distill_v2/checkpoint_evidence | head -5
ls distill_v2/gates 2>/dev/null | head -5
