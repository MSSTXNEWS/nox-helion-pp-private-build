echo "C300: d_b1"
B=/workspace/nox/web/build; export PATH=/workspace/nox/tools/node/bin:$PATH
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/d_build_vendor.mjs -o $B/d_build_vendor.mjs
cd $B; nohup setsid node d_build_vendor.mjs > build_vendor.log 2>&1 &
sleep 100; tail -60 $B/build_vendor.log; df -BG /workspace|tail -1
