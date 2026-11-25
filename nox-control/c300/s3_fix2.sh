#!/bin/bash
D=/workspace/nox/web/site/qa/rework; mkdir -p $D
echo "nav (S3 $(date +%F)): меню 72->33, Dock-списки в стекле, чёрное солнце+пульт, Ctrl+K/лупа с командами и синонимами, трансляция/второй экран, View Transitions. Не сделано: Meilisearch, серверные команды громкость/проектор/перезапуск (нет эндпоинтов), проверка 4K только на переполнение" > $D/nav.fixed
echo "settings (S3 $(date +%F)): макет macOS на Shoelace, 7 вкладок на живых данных, 5 миров и 6 палитр, 3D-планеты three.js (фото-текстуры только у Земли и Луны: нет vendor/planets)" > $D/settings.fixed
ls -la $D/nav.fixed $D/settings.fixed; ls /workspace/nox/web/site/vendor/planets 2>&1 | head -5
