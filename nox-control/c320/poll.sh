#!/bin/bash
cd /root/nox/state/flash_bench; for f in $(ls -t *.json | head -4); do echo "== $f $(cat ${f%.json}.cfg 2>/dev/null)"; python3 -c "
import json,sys;d=json.load(open('$f'));print({k:(v if k not in('short_text','long_text') else v[:60]) for k,v in d.items()})" 2>&1 | cut -c1-900; done; ls *.done | tr '\n' ' '; pgrep -af flash_bench.py | wc -l; tail -c 300 *.err 2>/dev/null | tail -3
