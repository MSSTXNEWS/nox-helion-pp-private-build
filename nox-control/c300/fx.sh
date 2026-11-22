#!/bin/bash
Q=/root/nox/repo/nox-control/qs6; sed -n 190,262p $Q/memory_layer.py | cut -c1-190
grep -n "self.create\|memory_on\|def _open\|writable\|read_only\|mode=ro" $Q/memory_layer.py | head -12 | cut -c1-160
tail -5 /root/nox/logs/gateway.log | cut -c1-200
