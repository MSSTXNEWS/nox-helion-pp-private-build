W=/workspace/nox/web/pkg/server
wc -l $W/creative_proxy.py $W/svc_proxy.py
cat $W/creative_proxy.py | cut -c1-230 | head -120
grep -n "8104\|vision\|/v1/chat" $W/svc_proxy.py | head -20 | cut -c1-200
