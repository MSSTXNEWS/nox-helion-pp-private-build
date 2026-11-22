#!/bin/bash
cd /root/nox/state/flash_bench; date +%H:%M; ls ALL.done 2>/dev/null; pgrep -f flashopt.py >/dev/null && echo alive || echo DEAD
tail -n 5 driver.log | cut -c1-420; tail -n 3 driver.out | cut -c1-200
