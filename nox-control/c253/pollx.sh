#!/bin/bash
sleep 200; cut -c1-330 /root/nox/logs/B_exp.out | tail -14; cat /proc/loadavg
