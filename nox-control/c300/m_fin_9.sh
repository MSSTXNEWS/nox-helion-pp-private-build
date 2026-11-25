for i in $(seq 1 6); do c=$(curl -s -o /dev/null -w "%{http_code}" 127.0.0.1:8091/web/index.html); [ "$c" = 200 ] && break; sleep 8; done; echo "OUT: server $c"
