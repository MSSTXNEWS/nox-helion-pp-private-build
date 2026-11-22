#!/bin/bash
grep -rln "ОЗУ свободно\|аптайм" /root/nox/repo/nox-control /root/nox/*.py /root/nox/dl/v7/core/nox_wow 2>/dev/null | grep -v "\.pyc\|test_\|bak" | head -8
grep -rn "аптайм" /root/nox/repo/nox-control/wow7 2>/dev/null | grep -v "\.pyc\|test_" | head -3 | cut -c1-220
