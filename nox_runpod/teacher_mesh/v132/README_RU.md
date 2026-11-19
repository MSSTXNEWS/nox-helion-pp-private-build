# NOX HELION V132 · ONEPASS SAFE SOURCE · 15.11.2026

Это **исходный проверяемый комплект продолжения существующего NOX**, не второй сервер, не новая модель и **не готовый установленный Windows-релиз**.

## Точка входа

- Исходный репозиторий: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/256
- Существующий OneHost: Vast.ai #60509551; один основной NOX, штатная S03 и её SQLite.
- Ранее подтверждённые 23/92 прямых WEB API — только инвентаризация (не полная функциональная приёмка).
- В действующем NOX подтверждены авторизованный WEB и настоящий потоковый чат с S03: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43650893956

## Что в комплекте

1. Реальный модуль POST `/api/nox/memory/facts` для двух страниц WEB V29.3 (чат и память) на исходном `s03_memory.remember()`; проверка owner-cookie, SHA текста, внутреннего хеша S03, provenance, STOP, идемпотентности и readback.
2. SHA-закреплённый установщик V130: существующие `chat_proxy.py` и `nox_v29_chat_bridge.py`, backups+rollback, *без создания второй базы, сервера или модели*.
3. Матрица всех 92 WEB API с делением по реальному хосту: OneHost, Windows PC, внешнее согласие и неуточнённые маршруты. Нет фальшивых 200 и процентных PASS.
4. Единый read-only proof-gate V132, проверка Vast, существующий восстановительный код V61 и Windows ONEPASS V70.
5. `Windows_Offsite/` содержит оба обязательных файла V70 **вместе с** `windows_offsite_receiver.ps1`, прежде находившимся в другом каталоге.

## Установка без потерь

**Сначала восстановить доступ:** последняя независимо проверенная Vast API-квитанция получила `auth_error` на GitHub Actions secret `NOX2` (https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/256#issuecomment-6885941004). Это не доказательство удаления экземпляра. Владелец перевыпускает ключ в https://console.vast.ai/manage-keys/ и обновляет **существующий** GitHub secret `NOX2` внутри https://github.com/MSSTXNEWS/nox-helion-pp-private-build/settings/secrets/actions . Никакие ключи не присылать в чат, код или журналы.

Затем **только ручной** workflow `.github/workflows/nox-v132-onepass-safe.yml`: сначала источник и реальный API admission; нативная операция допускается лишь по `allow_native=YES` и совпадающим SHA одного действующего сервера. При дрейфе исходников, занятости модели, STOP, недоступности SQLite или ошибке внешней авторизации — HOLD без установки.

**Windows:** в распакованном каталоге `Windows_Offsite/` находится `NOX_V70_ONEPASS_PC.cmd`; он вызывает соседние PowerShell-скрипты и проверяет только зашифрованные копии с оригинального Google Drive при наличии Google Drive Desktop/rclone. Пакет не содержит тяжёлых данных; реальные части берутся из авторизованного Drive. Сохранение ciphertext НЕ равно расшифровке закрытым ключом, восстановлению optimizer или успешной физической приёмке Windows.

## Точный статус

WEB полный 92/92 E2E: **HOLD**. Собственные full-parameter веса и optimizer шага с checkpoint: **HOLD**. Внешний restore S03/checkpoint: **HOLD**. Реальный Windows E07: **HOLD**. Физическая активация V130: **HOLD_AUTH** до восстановления NOX2. Статус исходников: подтверждается только машинной квитанцией V132 GitHub Actions.

Версия правил Notion: `instructions_version 0.0.6`. Бинарные веса, пароли, cookie и личные записи в архив не включаются.
