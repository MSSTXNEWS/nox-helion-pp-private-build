#!/bin/bash
Q=/root/nox/repo/nox-control; sed -n 14,22p $Q/glm53/gateway.py; sed -n 120,150p $Q/glm53/gateway.py | cut -c1-200
grep -n "def prepare\|def __init__\|def journal\|def remember\|def observe\|def after\|def record" $Q/qs6/memory_layer.py | cut -c1-150
grep -n "MemoryLayer(" $Q/glm53/gateway.py | cut -c1-200
grep -n "mem\.\w*(" $Q/glm53/gateway.py | grep -v "journal" | cut -c1-170 | head -12
