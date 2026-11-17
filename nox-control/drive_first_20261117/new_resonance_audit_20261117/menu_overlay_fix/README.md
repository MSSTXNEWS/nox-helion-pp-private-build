# Исправление перехода в основной чат внутри существующего mount

Статус: **SOURCE_TESTED, сервер не изменён**.

Серверная проверка `44172726307 / 134355830401` подтвердила HTTP 200 для
`/nox-web-v29/chat.html` и HTTP 401 для `/nox/chat` в той же авторизованной
сессии. Полные bytes отданного `nox-ui.js` совпали с существующим owner overlay:
`18d8c8d6009323188b9f903920308b3b871a6123f7b425a77184a6b2c147640e`.
Его `routeLinks` превращает относительные ссылки `chat.html` в этот alias 401.
Фактический браузерный клик меню отдельно не проверялся.

## Единственное изменение

`MENU_CHAT_ROUTE.patch` добавляет одну пару в `_V122_OWNER_UI_PATCHES`.
Для владельца внутри `/nox-web-v29/` ссылка на страницу `chat` ведёт в
`/nox-web-v29/chat.html`; query и fragment сохраняются. Другие страницы,
публичный режим, внешние ссылки и работа за пределами mount сохраняют поведение.
Исходный frozen `nox-ui.js` и его pin `c5f6b23d…` остаются прежними.

После этой единственной дополнительной подстановки ожидается отданный JS:
43 021 байт, SHA256
`13897495d7c9c628ef4f3094fafdad5f5932a3570d21c650112ba7138ab3c2f0`.

## Точный контекст и внедрение

Patch построен на сохранённом историческом bridge SHA256
`3cd548a69ac0fa7128368bef77f5f7ef032359128cf723eaca1c6a0514c85dc6`.
`historical_native_v29_bridge.candidate.py` — только воспроизводимый исходный
контекст для локальной проверки. **Его нельзя целиком копировать на сервер:**
актуальный O1 bridge имеет SHA256
`17932e2f49a659119593e6819acf945ebbedfb274595b8086f1031096b7d2a0f`
и содержит более поздние исправления чата/S03.

Следующий шаг принадлежит O1/root: взять точный актуальный bridge под действующим
claim, перенести только добавленную пару в существующий serving overlay,
сохранить остальные изменения и выполнить штатную проверку/установку. Затем
сопоставить отданный JS с ожидаемым hash и проверить переход меню в основной чат.
Авторизацию, alias сервера, модель и источник frozen JS эта правка не меняет.

## Проверка

`python -m unittest -v test_menu_overlay.py`: 2/2 теста пройдены. Первый связывает
baseline с полным реально отданным JS и доказывает единственную дополнительную
подстановку. Второй выполняет извлечённый `routeLinks` в изолированном Node VM:
9 случаев проверяют нужный переход, query/fragment и границы изменения.
Тест использует сохранённые входы из `history_contract_reuse` и
`web29_original_chat_audit_20261117`, закреплённые в `PATCH_RECIPE.json`.

### Переносимое воспроизведение опубликованного патча

Тест принимает `NOX_MENU_BASE_SOURCE`, `NOX_MENU_RAW_UI` и
`NOX_MENU_CANDIDATE_SOURCE`. До разбора AST и выполнения выбранных чистых
функций он проверяет полные SHA исходника и кандидата по `PATCH_RECIPE.json`.
Полный SHA frozen JS также проверяется до этих операций. Локальные пути остаются
только значениями по умолчанию.

В репозитории исторический вход —
`nox_runpod/teacher_mesh/v112/native_v29_full_bridge.py`, SHA256 `3cd548a6…`.
Исходный JS берётся из `site/nox-ui.js` канонического V13 ZIP, SHA256
`c5f6b23d5fc6c31c4c388a574bfa8c61243cda6000cefb0026732ebe4183b765`.
Полный архив V13 имеет SHA256
`f12a6f36e9718ee483e0d9d2e3f16aa41c3911ec9ef6e2bc03502a5da0d62fe4`.
Архив и historical candidate не требуется дублировать в публикации.

Из корня репозитория задайте абсолютные пути к каталогу опубликованного патча
и уже полученному архиву, затем выполните:

```bash
export NOX_MENU_BASE_SOURCE="$PWD/nox_runpod/teacher_mesh/v112/native_v29_full_bridge.py"
nox_menu_patch_dir="/absolute/path/to/published/menu_overlay_fix"
nox_v13_archive="/absolute/path/to/NOX_HELION_WEB_WOW_MAX_V13_UNIFIED_20261117.zip"
nox_menu_fixture_dir="$(mktemp -d)"
cp "$NOX_MENU_BASE_SOURCE" "$nox_menu_fixture_dir/nox_v29_chat_bridge.py"
git -C "$nox_menu_fixture_dir" apply -p1 "$nox_menu_patch_dir/MENU_CHAT_ROUTE.patch"
unzip -p "$nox_v13_archive" site/nox-ui.js > "$nox_menu_fixture_dir/nox-ui.js"
export NOX_MENU_RAW_UI="$nox_menu_fixture_dir/nox-ui.js"
export NOX_MENU_CANDIDATE_SOURCE="$nox_menu_fixture_dir/nox_v29_chat_bridge.py"
python "$nox_menu_patch_dir/test_menu_overlay.py" -v
```

`git apply -p1` применяется только к временной копии исторического исходника.
Эта команда воспроизводит candidate для теста и не устанавливает его на сервер.

Native/model запросов и изменений production при подготовке: 0.
