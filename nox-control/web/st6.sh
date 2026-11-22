#!/bin/bash
cd /root/nox/repo/nox-control/wow7/brain
grep -n "confirm\|подтверд\|превью\|preview\|pending\|forget\|удал" actions.py nox_core.py executors.py | cut -c1-170 | head -50
