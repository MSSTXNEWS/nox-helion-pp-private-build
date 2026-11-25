echo "C300: k_url1"
cat /proc/1/environ 2>/dev/null | tr '\0' '\n' | grep -E '^(PUBLIC_IPADDR|VAST_TCP_PORT_18091|VAST_TCP_PORT_8091|VAST_TCP_PORT_8080|VAST_TCP_PORT_443|VAST_TCP_PORT_80)=' 
env | grep -E '^(PUBLIC_IPADDR|VAST_TCP_PORT_)' | head -20
grep -rhoE "https?://[a-z0-9.-]+(trycloudflare|ts\.net|nox[a-z0-9.-]*)[^ \"']*" /workspace/nox/state/*.json /workspace/nox/state/*.txt 2>/dev/null | sort -u | head -5
