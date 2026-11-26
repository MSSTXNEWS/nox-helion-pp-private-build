echo "C300: ac_ab3"
D=/workspace/nox/tmp/ab
sleep 150; cat $D/res.txt
P=$(pgrep -f "port 8104"|head -1); tr '\0' '\n' </proc/$P/environ | grep -E "LLAMA_ARG|LLAMA_" | head
S=$(pgrep -f "llama-swap -config"); echo swap $S cwd $(readlink /proc/$S/cwd) etimes $(ps -o etimes= -p $S); curl -s -m3 127.0.0.1:8200/running | head -c 300
