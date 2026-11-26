echo "C300: w_p5"
N=/workspace/nox; export PATH=$N/tools/node/bin:$PATH
tail -2 $N/agent/out/w_p4.log | cut -c1-120
python3 $N/tools/uiscore/report.py 2>&1 | grep -E '^[a-z0-9-]+ +U=' | sed 's/ | V.*lh/ lh/;s/ ; V.*//' | cut -c1-80
