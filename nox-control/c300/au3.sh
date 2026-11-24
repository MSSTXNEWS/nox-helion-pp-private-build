#!/bin/bash
cd /workspace/nox/web/site
grep -hoE "['\"\`][./]*(vendor|lib)/[a-zA-Z0-9._@/-]+\.(js|css|mjs)['\"\`]" nox-p-work.js nox-p-widgets.js nox-p-cinema.js nox-registry.js projects.html calendar.html board.html constructor.html cinema.html widgets.html assistant.html 2>/dev/null | tr -d "'\"\`" | sort -u | while read f; do p=${f#./}; [ -e "$p" ] && echo "OK  $p" || echo "MISS $p"; done | sort | head -60
ls /workspace/nox/web/pkg | head; ls /workspace/nox/web/pkg/../ ; find / -name "NOX_WEB_VENDOR.zip" -not -path "*/proc/*" 2>/dev/null | head -3
