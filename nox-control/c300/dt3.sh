#!/bin/bash
sed -i 's/await pg.hover(".nw-cat:nth-child(5) .nw-btn")/await pg.keyboard.press("Escape"); await pg.hover(".nw-cat:nth-child(5) .nw-btn", force=True)/' /tmp/dt.py
timeout 200 /workspace/nox/venv/bin/python /tmp/dt.py 2>&1 | grep -v "^ " | tail -8
