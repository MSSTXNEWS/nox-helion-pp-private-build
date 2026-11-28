echo "K1: hc2"
for p in $(pgrep -f body_restart.sh); do echo "br pid=$p etime=$(ps -o etimes= -p $p) args=$(ps -o args= -p $p | grep -oE -- '--(cmd|force)[^ ]*( [^ ]*)?' | sed 's#.*/##' | tr '\n' ' ')"; done
for p in $(pgrep -f llama-server); do echo "ls pid=$p etime=$(ps -o etimes= -p $p) port=$(ps -o args= -p $p | grep -oE -- '--port [0-9]+' ) ncmoe=$(ps -o args= -p $p | tr '\n' ' ' | grep -oE -- '--n-cpu-moe [0-9]+')"; done
ss -ltn 2>/dev/null | grep -c ':8104 ' | sed 's/^/listen8104=/'
echo "h8104=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health)"
echo END
