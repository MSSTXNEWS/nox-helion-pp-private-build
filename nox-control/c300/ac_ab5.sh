echo "C300: ac_ab5"
D=/workspace/nox/tmp/ab; cat $D/res.txt | cut -c1-70; pgrep -af "ab2.sh|ab.sh|port 8190" | cut -c1-80
pgrep -af "llama-swap -config" | cut -c1-120; curl -s -m3 127.0.0.1:8200/running | head -c 100; echo
