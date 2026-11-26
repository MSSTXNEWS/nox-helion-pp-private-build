echo "C300: w_d4"
N=/workspace/nox; export PATH=$N/tools/node/bin:$PATH
tail -3 $N/agent/out/w_d3.log | cut -c1-200
python3 $N/tools/uiscore/report.py 2>&1 | grep -E '^(qa|live|studio|tv|settings|system|memory|writer|chat|chat-dc|calendar|photo|board|about|advisors|ai-learning|assistant|atlas|benchmark|book-reader|browser) ' | cut -c1-175
