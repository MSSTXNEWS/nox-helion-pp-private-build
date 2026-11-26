#!/bin/bash
A=/workspace/nox/agent
ls $A/autotrain | head -40; echo ==; wc -l $A/ckpt_guard.py; sed -n 1,60p $A/ckpt_guard.py | cut -c1-200
echo == gates; ls $A/autotrain/*gate* $A/*gate* 2>/dev/null; grep -ln "NO_GAIN" -r $A --include=*.py 2>/dev/null | head
