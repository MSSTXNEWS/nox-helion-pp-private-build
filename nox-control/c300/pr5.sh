#!/bin/bash
cd /root/nox/repo/nox-control/glm53 && NOX_WOW7=/root/nox/repo/nox-control/wow7 NOX_STATE=/root/nox/state PYTHONPATH=/root/nox/repo/nox-control timeout 60 python3 -c "
import gateway_prime as G
p=G.make_prime()
print('prime ok', type(p).__name__, sorted(getattr(p,'parts',{}).keys()) if hasattr(p,'parts') else '')
" 2>&1 | tail -8 | cut -c1-200
ls -t /root/nox/logs | head -5
