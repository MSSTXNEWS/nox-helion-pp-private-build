#!/bin/bash
G=/workspace/nox/advisors/gateway.py
sed -n 1,82p $G | sed -E 's/(sk-|ghp_|key-)[A-Za-z0-9_-]{8,}/\1***/g' | cut -c1-260
sed -n 93,134p $G | cut -c1-240
