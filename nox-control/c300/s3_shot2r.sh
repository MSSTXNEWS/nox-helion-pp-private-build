#!/bin/bash
for i in $(seq 1 25); do pgrep -f s3_shot2.py >/dev/null || break; sleep 10; done
for v in d m; do echo "=== $v"; cut -c1-900 /tmp/s3_shot2_$v.out; done
