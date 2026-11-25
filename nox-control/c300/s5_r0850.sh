tail -c 200 /tmp/s5_chain5.log | tr "\n" " " | sed "s/^/OUT: c5 /"
