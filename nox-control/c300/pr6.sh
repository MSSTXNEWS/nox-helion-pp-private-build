#!/bin/bash
grep -iE "prime|error|Traceback" /root/nox/logs/restart_8082.log | tail -6 | cut -c1-160; echo lines=$(wc -l < /root/nox/logs/restart_8082.log)
