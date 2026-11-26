echo "C300: srv_k48"
cd /workspace/nox
F=$(timeout 20 grep -l "def loss_bw" ops/*.py distill_v2/code/*.py 2>/dev/null | head -2); echo F=$F
for f in $F; do awk '/def loss_bw/{p=1} p{print; n++} n>45{exit}' $f | cut -c1-200; done
echo == draw
grep -n "def local_generate" -A40 ops/draw/invoke_draw.py | cut -c1-210 | head -60
ls ops/draw | head; which sd sd-cli 2>/dev/null; ls /workspace/stable-diffusion.cpp/build/bin 2>/dev/null | head
