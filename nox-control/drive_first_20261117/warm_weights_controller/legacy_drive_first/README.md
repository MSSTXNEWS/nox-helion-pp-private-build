# Точечный Drive-first патч существующего teachers warm

Цель — закрыть старый путь **HF → RAM**, сохранив `/root/nox/ops/nox_teachers_warm.sh`, его startup-вызовы, текущие веса и пути. Новый daemon или scheduler не создаётся. Installer меняет только bytes существующего shell-скрипта; manifest, cron, onstart и Supervisor не переписывает, warm-script не запускает.

## Проверенные исходники

Байты получены из файлов Drive, ссылки предоставлены основным исполнителем:

| Файл | SHA256 |
|---|---|
| [nox_teachers_warm.sh](https://drive.google.com/file/d/1r5jIOB2ykM7OsxyYRAk4TMaE5i3wOTly/view) | `437739550dbdff28380a95302c1cc1e98ceab3f147de898b40dd8ec82ef80389` |
| [TEACHERS_MANIFEST_20261117.json](https://drive.google.com/file/d/1AqJun2kWY5qWJtV1eZ8gY7WFgTJVOLqG/view) | `237deb2a93c53de9d73501bc572f62af2565c45b8a895382a183685434199093` |
| Исправленный shell-скрипт | `14ec1196f61813ff6c88b1854a479660e7ef445fe7f5cb78c6f46e315dbf81e2` |

Оба исходных SHA совпадают с [историческим отчётом t145u](https://drive.google.com/file/d/19zhlsEo9TsLE2XhgwR3ycWH9qy3cTdd-/view). Это проверка Drive-копий. **Текущий native SHA этим пакетом не получен.** Перед apply основной исполнитель обязан прочитать его с сервера заново. Любое отличие от pinned исходника требует нового точечного патча, а не принудительной замены.

В исходном manifest шесть teacher/judge объектов имеют `upload_blocked_uploadfile_100mb_limit`, остальные четыре — `pending_exec09`. Эти исторические значения сохраняются. Отдельный [parts-manifest vision/whisper](https://drive.google.com/file/d/1iQ7eHb0sxBp3gQYmKe6fYl0w4PZ-ND7d/view) не заменяет проверенный ID полного объекта; здесь его содержимое и сборка частей не проверялись.

## Изменения

- Удалены `download_one`, curl, HF URL selection и public/uc URL fallback. `hf_url` больше даже не извлекается в shell. Историческое поле в исходном JSON остаётся данными о происхождении.
- Новый объект разрешён только с real whole-object `drive_id`, pinned size/SHA и совпадающим `drive_verification` receipt. Если binding или настроенный `noxdrive:` отсутствует — HOLD, внешних fallback нет.
- Единственная transfer-команда — `rclone backend copyid noxdrive: ID PART`. Colon исправлен по [официальному контракту rclone copyid](https://rclone.org/drive/#copyid); destination может быть локальным путём.
- Уже существующий файл с совпадающим размером пропускается без SHA loop и повторной загрузки. Это **проверка размера**, а не новое доказательство SHA.
- Существующий файл с другим размером, чужой/старый `.part` или отличающийся symlink сохраняются и дают HOLD. Оригинальный вариант удалял файл неправильного размера и заменял symlink.
- Новый скачанный файл проходит size/SHA; публикация — `ln -T` без перезаписи, затем удаляется только собственное второе имя `.part`. При ошибке SHA partial сохраняется для reconciliation.
- При конфликте уже существующего файла symlink-изменения не выполняются. Основные пути `/dev/shm/nox_t802u` и `/root/nox/models` сохранены.

### Receipt для нового полного объекта

`drive_verification` — обязательное поле в доверенном manifest row. Оно должно содержать **фактическую** квитанцию проверки объекта Drive:

| Поле | Требование |
|---|---|
| `verified` | Boolean `true`, только после реального readback/проверки Drive |
| `drive_id` | ID проверенного полного объекта, совпадает с row.drive_id |
| `size` | Совпадает с pinned полным размером |
| `sha256` | Совпадает с pinned SHA256 row |
| `receipt_id` | Непустой ID реальной квитанции |
| `verified_at` | Время реальной проверки |

Этот патч не проставляет выдуманные квитанции или file IDs. При текущем историческом manifest отсутствующие модели дадут HOLD; уже тёплые файлы будут сохранены. Parts-only upload сначала требует проверенной сборки/описания полного объекта через действующую систему Drive.

## CAS installer

`install.py` по умолчанию выполняет только check. Apply требует явный `--expected-source-sha`, проверяет current bytes, создаёт backup без перезаписи, повторно проверяет текущий файл под lease, атомарно публикует известный patched SHA и делает readback. Mode/uid/gid сохраняются.

Используется только уже существующий `/root/nox/state/owner_maintenance.lock` с `flock(LOCK_EX|LOCK_NB)`. Missing/busy lock даёт HOLD, новый lock-файл не создаётся. При уже удерживаемом root-maintenance lease можно передать его настоящий inherited fd через `--maintenance-lock-fd`; проверяются device/inode, borrowed fd не закрывается и не разблокируется.

Порядок на сервере для основного исполнителя:

1. Новый read-only `sha256sum /root/nox/ops/nox_teachers_warm.sh`. Сверить с pinned Drive source и осмотреть работающий legacy warm процесс; опубликованный патч не изменяет уже выполняющийся shell.
2. `python3 legacy_drive_first/install.py` — check без выполнения warm.
3. Только при совпадении нового native readback с pinned source: `python3 legacy_drive_first/install.py --apply --expected-source-sha 437739550dbdff28380a95302c1cc1e98ceab3f147de898b40dd8ec82ef80389` под существующим maintenance lease.
4. Сохранить returned receipt. Ожидаемый статус `PATCH_APPLIED_NOT_EXECUTED`; это не свидетельство загрузки моделей или работы TRAIN.

Installer не перезапускает Supervisor, не правит cron/onstart, не останавливает процессы, не запускает сеть и не трогает веса. Backup расположен рядом со скриптом: `nox_teachers_warm.sh.before-drive-first-437739550dbdff283.bak`. Автоматического rollback с повторным включением HF fallback нет.

## Проверка и границы

```bash
python3 legacy_drive_first/build_patch.py
bash -n legacy_drive_first/nox_teachers_warm.drive_first.sh
python3 -m unittest discover -s legacy_drive_first/tests -v
```

**Два targeted теста PASS.** Временные локальные fixtures подтверждают: отсутствующий Drive binding/config блокирует transfer; готовые файлы и несовпадающие файлы сохраняются; существующие файлы не хешируются повторно; HF URL не вызывается даже после Drive failure; Drive fixture проходит SHA и публикацию. В том же fixture проверены CAS mismatch, busy lock, backup/readback, сохранение mode и повторный idempotent apply. Все rclone/curl в тестах — записывающие команды локальные fixtures, сетевых model downloads нет.

Это узкое исправление источника существующего startup. Старый tmpfs free-space admission сохраняется; полное cgroup/PSI/owner/resource-lease управление реализовано в соседнем `nox_warm` контроллере и требует отдельного настоящего host binding. Этот патч не объявляет legacy startup безопасным для произвольного объёма загрузок при текущем headroom. Native apply, загрузки весов и изменения сервисов в рамках разработки **не выполнялись**.
