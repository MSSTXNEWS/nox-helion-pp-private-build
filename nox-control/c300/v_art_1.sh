echo "C300: v_art_1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300; A=/workspace/nox/advisors
for f in gateway.py register.py; do cp $A/$f $A/$f.bak_v_art; done
curl -fsSL "$R/v_gw_gateway.py?$(date +%s)" -o $A/gateway.py.new && mv $A/gateway.py.new $A/gateway.py
curl -fsSL "$R/v_gw_register.py?$(date +%s)" -o $A/register.py.new && mv $A/register.py.new $A/register.py
curl -fsSL "$R/v_art_art.py?$(date +%s)" -o $A/art.py.new && mv $A/art.py.new $A/art.py
curl -fsSL "$R/v_art_selftest.py?$(date +%s)" -o $A/art_selftest.py.new && mv $A/art_selftest.py.new $A/art_selftest.py
pkill -f advisors/gateway.py; sleep 1
setsid nohup python3 $A/gateway.py >/workspace/nox/svc/logs/advisors.log 2>&1 </dev/null &
sleep 3; curl -s -m5 127.0.0.1:8793/health | head -c 120; echo
setsid nohup python3 $A/art_selftest.py >$A/art_selftest.log 2>&1 </dev/null &
sleep 200; cat $A/art_selftest.log | cut -c1-400; tail -3 /workspace/nox/svc/logs/advisors.log | cut -c1-200
echo END
