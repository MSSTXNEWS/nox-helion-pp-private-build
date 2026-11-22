#!/bin/bash
S=/root/nox/dl/v7/core/nox_wow/DEPLOY/staged/nox-control/wow7; W=/root/nox/repo/nox-control/wow7
ls $S | tr '\n' ' '; echo
for m in affect_loop nox_workspace nox_self_model_live beliefs development; do find $S -name "$m.py" | head -1; done
grep -n "не подключён\|import_module\|sys.path" /root/nox/repo/nox-control/glm53/gateway_prime.py /root/nox/repo/nox-control/glm53/nox_prime.py 2>/dev/null | head -12 | cut -c1-180
