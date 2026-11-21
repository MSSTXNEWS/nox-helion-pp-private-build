#!/bin/bash
R=/root/nox/repo; git -C $R pull -q 2>/dev/null || git clone -q --depth 1 https://github.com/MSSTXNEWS/nox-helion-pp-private-build $R
bash $R/nox-control/c122/boot_s1.sh install; timeout 100 bash $R/nox-control/c122/boot_s1.sh 2>&1 | tail -20; tail -3 /root/nox/dl/logs/deps.log
