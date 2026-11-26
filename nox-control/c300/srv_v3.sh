#!/bin/bash
sed -n 17,54p /workspace/nox/svc/pipeline/pipeline_svc.py | cut -c1-240
grep -n "^BUDGET" /workspace/nox/svc/pipeline/pipeline_svc.py
