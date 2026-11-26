#!/bin/bash
F=/workspace/nox/web/pkg/server/chat_core.py
sed -n 436,470p $F | cut -c1-260
grep -n -E "^RACE|RACE_[A-Z_]* *=|race_lim|lim *=" $F | head
