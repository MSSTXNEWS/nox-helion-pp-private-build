#!/bin/bash
for i in $(seq 1 24); do pgrep -f s3_shot5.py >/dev/null || break; sleep 10; done
grep "^INFO" /tmp/s3_shot5.out | cut -c1-300
for t in scene_d set_m scene_m scene_k set_k radial_d; do f=/tmp/s3_5_$t.jpg; [ -f $f ] || continue; ffmpeg -loglevel error -y -i $f -vf scale=620:-1 -q:v 16 /tmp/s3_5r_$t.jpg; echo "B64_${t}_BEGIN"; base64 -w 900 /tmp/s3_5r_$t.jpg; echo "B64_${t}_END"; done
