#!/bin/bash
cd /root/nox/dl/v7/exec/nox_wow
sed -n '1,400p' INSTRUCTION_FOR_EXECUTOR_V7.md | grep -n . | head -300
