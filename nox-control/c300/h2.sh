#!/bin/bash
cd /root/nox/web; grep -n "tiers\b\|tiers =\|tiers=\|fetch(" nox-shell.js | head -12 | cut -c1-240
