#!/bin/bash
tail -400 /workspace/nox/state/pipe_err.log | grep -o "ms=[0-9]* ok=[A-Za-z]*" | awk '{split($1,a,"=");ms=a[2];n++;s+=ms; if(ms>10000)o++; if($2=="ok=True")k++} END{print "n",n,"avg_ms",s/n,"over10s",o,"ok",k}'
tail -5 /workspace/nox/state/pipe_err.log | cut -c1-200
sed -n 520,535p /workspace/nox/web/pkg/server/chat_core.py | cut -c1-240
