#!/bin/bash
cd /root/nox/web; grep -n "НЕ ЗАГРУЖЕН\|не загружен" *.js *.html 2>/dev/null | cut -c1-260 | head
