#!/bin/bash
grep -rlI "Тортилла-7\|Тромсё" /root/nox/memory /root/nox/logs /root/nox/state 2>/dev/null | head; ls /root/nox/memory | head -20
