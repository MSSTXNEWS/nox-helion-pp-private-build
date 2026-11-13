# NOX HELION WEB WOW V29.3 — физически проверенный комплект

Дата: 13.11.2026 · Канонический исходный PR: #251.

**Единый ZIP:** [NOX_HELION_WEB_V29_3_FROZEN_20261113.zip — скачать упаковку GitHub Actions](https://drive.google.com/file/d/1A0ZAb8nsqpWlv7PZEUDcyQKV3kSbeCsI/view). Первый уровень ZIP — упаковка GitHub; внутри единственный настоящий архив **85 218 272 байта**, SHA-256 `166becb90fce63e2db3f9a74281d756995844552cddb7b67a0ac4bd67a190aa0`.

**Воспроизводимый комплект:** [NOX_V29_3_OFFLINE_REBUILD_AND_WINDOWS_STAGE_20261113.zip — скачать упаковку GitHub Actions](https://drive.google.com/file/d/1PtSvooSPHll8-F4l9iq-Z_iGi0-i5uZ4/view). Внутренний ZIP — **27 213 байт**, SHA-256 `ee52e35023c65e1a1cdd045958d425ca8c0d827091536f2c2e2fd3b82286be10`. Внутри 15 файлов: исходники frozen, контроль SHA, build/verify, CMD и Windows staging. Он **сам воспроизводит в точности** основной ZIP из [V28 источника](https://drive.google.com/file/d/1YBOJYNzvsjnhzg5TAZj7iL2h543NgOe0/view).

## Проверки

- Два независимых Linux build + дополнительный rebuild непосредственно из офлайн-комплекта: точный SHA совпал во всех трёх.
- SHA и ZIP CRC: 1089 записей; 1085 SourceLock-записей физически проверены. Оригинальный D02 и неизменённые исходники защищены.
- Настоящий GitHub Actions Windows Runner: скачал исходный 85-МБ архив, проверил точный SHA, весь SourceLock и распаковал 1089 файлов только в отдельный staging — **PASS**: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43441913621 .
- Тесты Chromium 5/5, PC API 16, локальные статические маршруты 17/17, страницы HTML 38 без битых ссылок.

## Безопасный запуск на ПК

Режим проверки уже собранного архива: поместите внутренний V29.3 ZIP в `C:\NOX\incoming`, выполните `NOX_V29_3_WINDOWS_STAGE.ps1` из комплекта с `-InspectOnly` либо без него для **изолированной** распаковки только в `C:\NOX\builds`. Никаких живых файлов/баз/весов он не изменяет.

Для полного воспроизведения из исходников: поместить V28 ZIP в `C:\NOX\incoming`, запустить `NOX_V29_3_REBUILD.cmd` из комплекта. Если готовый V29.3 ZIP уже существует, сборщик намеренно остановится без перезаписи.

**Непринятые физические гейты:** Windows WPF/WebView2 EXE, живой OneHost/Ollama STOP, история S03 после рестарта, RU/ES голос, GPU SAFE70 и обновления собственных весов NOX. Это не тестировалось на пользовательском `C:\NOX`; полный релиз остаётся HOLD.

Временные публично маршрутизируемые URL Vercel переноса отключены после успешной загрузки в приватные хранилища.
