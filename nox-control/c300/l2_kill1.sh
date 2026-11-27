echo "K1: l2_kill1"
kill 2174389; sleep 2; ps -p 2174391 -o pid,args | cut -c1-100; (echo > /dev/tcp/127.0.0.1/18215) 2>&1 && echo living_up
