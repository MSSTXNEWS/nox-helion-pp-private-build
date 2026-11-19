# NOX HELION — сохранение зашифрованных V60/V61 на жёстком диске Windows

Источник: каноническая папка Google Drive NOX HELION EXPRESS INTEGRATOR / 06_ПАКЕТЫ_И_ЭКСПОРТЫ.
Содержимое: 5 ZIP-файлов, в том числе V60 S03+WEB и четыре части V61 optimizer/checkpoints.
Никакие исходные файлы на Vast, модели и S03 скрипт не изменяет.

## Запуск владельцем

1. Распакуйте этот ZIP в отдельную папку Windows.
2. Убедитесь, что Google Drive для компьютера вошёл в ваш аккаунт и файлы NOX видны в проводнике, либо `rclone` уже настроен для вашего Google Drive.
3. Дважды нажмите `NOX_V66_COPY_OFFSITE_TO_PC.cmd`. Сценарий выбирает подходящий фиксированный диск, предпочитая несистемный, и создаёт `NOX_HELION\OFFSITE\V60_V61_20261114`.
4. Если появится `HOLD_GOOGLE_DRIVE_DESKTOP_OR_SIGNED_IN_RCLONE_REQUIRED`, текущий компьютер не имеет готового доступа к Drive. Не передавайте пароли, OAuth токены или закрытые ключи в чат; настройте Drive for Desktop на самом компьютере и повторите.
5. При наличии уже настроенного `rclone` и отсутствии Google Drive Desktop можно запустить вручную: `powershell -NoProfile -ExecutionPolicy Bypass -File .\windows_offsite_receiver.ps1 -RcloneRemote drive`, заменив `drive` именем вашего существующего remote. Новую авторизацию скрипт не создаёт.

## Приёмка

- V60 ZIP — точные размер 8 109 924 байта и SHA-256.
- V61 — точный размер ZIP каждой части и SHA-256 **содержимого** `NOX_V61_CIPHER.partNN`.
- Итоговая локальная квитанция `NOX_V66_PC_OFFSITE_SHA_RECEIPT.json`.
- `owner_private_key_decryption_verified=false`: правильный закрытый ключ не проверяется этим сценарием и не должен покидать ПК.
- ZIP с зашифрованными частями V61 не означает подтверждённое восстановление optimizer. Перед удалением originals требуется независимый `age -d` и restore SHA всех файлов.
- Исходные Windows/Google Drive копии не удаляются. Не запускайте на сервере `rm` по одному факту успешного копирования ZIP.

[Исторический проверенный реестр V60/V61 на Google Drive](https://drive.google.com/file/d/1UM9fNXz3TXyuSLRam3_KrEf5MP637IT0/view).
