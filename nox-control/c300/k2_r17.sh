echo "C300: k2_r17"
F=/workspace/nox/brain/BRAIN/identity/hooks.py
wc -l $F; grep -nE "qa-|qa_|def |environ|known|speaker|conversation|cid" $F | cut -c1-200 | head -60
