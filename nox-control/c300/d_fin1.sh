echo "C300: d_fin1"
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/d_fin1.py -o /tmp/d_fin1.py && python3 -I /tmp/d_fin1.py
du -sh /workspace/nox/web/site/vendor; df -BG /workspace|tail -1
