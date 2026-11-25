pkill -f p3_fluxtest.py; sleep 2; pkill -9 -f "bin/sd --diffusion" ; sleep 1
sed 's|flux_test.txt|flux_test2.txt|' /tmp/p3_fluxtest.py > /tmp/p3_fluxtest2.py
NOX_DRAW_FORCE=1 nohup setsid /workspace/nox/venv/bin/python /tmp/p3_fluxtest2.py >/tmp/p3_fluxtest2.err 2>&1 &
echo started clean test
