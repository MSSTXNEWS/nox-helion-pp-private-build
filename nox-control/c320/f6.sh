#!/bin/bash
date +%H:%M:%S; pgrep -af 'llama-server' | cut -c1-120; ss -ltnp | grep -E '808[0-9]' | cut -c1-110
grep -vE 'print_timing|release|launch_slot|update_slots|log_server_r|send_final|srv  ' /root/nox/state/flash_bench/base0.srv.log | tail -6 | cut -c1-200
dmesg 2>/dev/null | grep -iE 'killed|oom' | tail -3 | cut -c1-200
grep -E 'srv.*(exit|stop|signal|SIGTERM)' /root/nox/state/flash_bench/base0.srv.log | tail -3 | cut -c1-160
ps -eo pid,args | grep -E 'dispatch|watchdog|supervis|start_glm' | grep -v grep | cut -c1-150 | head -5
ls /root/nox/*.sh | head -30 | tr '\n' ' '
