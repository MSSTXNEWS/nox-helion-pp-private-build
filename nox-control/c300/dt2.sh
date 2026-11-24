#!/bin/bash
sed -i 's/("index.html","cinema.html","tools.html","chat.html","settings.html")/("index.html","chat.html","cinema.html","projects.html","memory.html","training.html")/' /tmp/dt.py
timeout 150 /workspace/nox/venv/bin/python /tmp/dt.py 2>&1 | tail -8
