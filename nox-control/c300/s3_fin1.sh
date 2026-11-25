#!/bin/bash
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
df -BG /workspace | tail -1
curl -fsSL "$RAW/fetch_frontend_donors.sh?v=$(date +%s)" -o /tmp/s3_fetch.sh && nohup bash /tmp/s3_fetch.sh > /tmp/s3_donors.log 2>&1 &
sleep 200; tail -8 /tmp/s3_donors.log | cut -c1-300
cat >> /workspace/nox/PROGRESS.md <<'P'

## S3 (меню, навигация, пульт, настройки) 2026-11-25
- Сделано: nav.json 72 -> 33 пунктов (11 категорий нижней панели + 8 системных в шапке), 8 дублей перенаправлены (резервные копии *.bak_s3_1), qa/menu_plan.md; выпадающие списки Dock в стекле (иконка+название+описание, избранное, шторка на мобильных); малое чёрное солнце nox-sun-x (клик открывает пульт), состояния NOXstate; пульт; Ctrl+K (избранное, недавние, команды шины); миры HELION/CHRONOS/SOMNIUM/FORGE/SYNAPSE и 6 палитр (nox-worlds); настройки в макете macOS на Shoelace с 3D-превью планет.
- Не сделано / остановился: «Транслировать» (Presentation API), лупа-Spotlight с командами по синонимам, Meilisearch, MediaPipe-жесты, Glance, ползунки личности (сервис TRAITS :8101 не запущен), 100 анимаций (zip на Диске не распакован), планеты без фото-текстур (ждём vendor/planets от D). Шина /api/cmd и ревизор переданы S4/S5. web_server.py и qa_audit.py не менялись.
P
echo progress_written
