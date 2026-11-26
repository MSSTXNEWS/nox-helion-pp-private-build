#!/bin/bash
F=/workspace/nox/web/pkg/server/chat_core.py
sed -n 470,515p $F | cut -c1-420
