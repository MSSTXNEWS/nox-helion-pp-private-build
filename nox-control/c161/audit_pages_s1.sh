#!/bin/bash
# c161: только чтение. Аудит страниц веба и живых API на S1 (кратко).
B=http://127.0.0.1:8091
for u in /glm/v1/models /glm/v1/nox/stats /glm/props /memory/health /stt/health /tts/health /api/health /api/nox/tasks /api/nox/progress /api/pc-metrics; do echo "$u $(curl -s -m6 -o /dev/null -w %{http_code} $B$u)"; done | tr '\n' ' '; echo
echo "mime sw.js: $(curl -s -m5 -o /dev/null -w '%{http_code} %{content_type}' $B/web/sw.js)"
echo "vendor: $(for f in split.js/split.min.js dexie/dexie.min.js nox-wow/sortablejs/Sortable.min.js nox-extra/fullcalendar.global.min.js nox-extra/fuse.min.js nox-extra/echarts.min.js fx/uPlot.iife.min.js nox-extra/pdf.mjs nox-extra/photoswipe.esm.js; do echo -n "$f=$(curl -s -m5 -o /dev/null -w %{http_code} $B/web/vendor/$f) "; done)"
echo "stats: $(curl -s -m6 $B/glm/v1/nox/stats | head -c 260)"
echo "memory: $(curl -s -m6 $B/memory/health | head -c 160)"
echo "stt: $(curl -s -m6 $B/stt/health | head -c 120)"; echo "tts: $(curl -s -m6 $B/tts/health | head -c 120)"
echo "nxw-bnav в новых страницах: $(grep -l nxw-bnav /root/nox/web/{index,projects,memory,training,models,system,settings}.html 2>/dev/null | tr '\n' ' ')"
echo "chat: toplink=$(grep -c toplink /root/nox/web/chat.html) notify=$(grep -c nox-notify /root/nox/web/chat.html) extras=$(grep -c 'nox-web-extras' /root/nox/web/chat.html)"
echo "bak-160: $(ls /root/nox/web/*.bak-160 2>/dev/null | wc -l)"
