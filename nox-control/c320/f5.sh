#!/bin/bash
cd /root/nox/state/flash_bench
curl -s -m 5 localhost:8081/health; echo
sed -i 's#python3 /root/nox/flash_bench.py $N > $O/$N.json 2>$O/$N.err#python3 /root/nox/flash_bench.py $N > $O/$N.json 2>$O/$N.err; echo rc=$? >> $O/$N.err#' /root/nox/flash_bench.sh
grep -c 'rc=' /root/nox/flash_bench.sh
(timeout 250 python3 /root/nox/flash_bench.py t1 40 > t1.json 2> t1.err; echo rc=$? >> t1.err) 
cut -c1-900 t1.json; tail -c 600 t1.err
