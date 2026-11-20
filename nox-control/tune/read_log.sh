#!/bin/bash
tail -20 /root/nox/logs/tune.log 2>&1; curl -s -m 4 -o /dev/null -w "8098 health %{http_code}\n" http://127.0.0.1:8098/health
