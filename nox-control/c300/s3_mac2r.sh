#!/bin/bash
for i in $(seq 1 20); do pgrep -f s3_mac2_shot.py >/dev/null || break; sleep 10; done
cut -c1-900 /tmp/s3_mac2_shot.out
