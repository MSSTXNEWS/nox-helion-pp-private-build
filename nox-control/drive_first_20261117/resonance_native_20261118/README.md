# Минимальный патч меню действующего Резонанса

Статус: **SOURCE_TESTED; native установка не выполнялась**.

`native_menu_overlay_transform.py` переносит ранее проверенную правку меню на
фактическую установленную ревизию bridge. Она принимает только полный файл
51 632 байта с SHA256
`17932e2f49a659119593e6819acf945ebbedfb274595b8086f1031096b7d2a0f`.
Это postimage существующей O1 установки
`be4750aae3cb456e09df0ddcb39fcf0fd1673bd1`, run44171616874.
Полный точный input найден в существующем O1 source handoff и успешно
проверен production-функцией без замены pins. Кандидат: 51 865 байт,
SHA256 `9d7475428ad8c553c756ca50280ac2363e7c03854abab285de560ae066d4586a`;
вставка составляет 233 байта. Оба полных SHA закреплены в коде.

## Поведение

Добавляется одна пара в существующий `_V122_OWNER_UI_PATCHES`. В основном
native mount относительная ссылка `chat.html` ведёт на
`/nox-web-v29/chat.html`; query и fragment сохраняются. Исправляется переход
на `/nox/chat`, для которого проверка run44172726307 получила 401 при 200
прямого main URL в той же сессии. Эта правка не исправляет сам alias.

Модуль не читает файлы, не исполняет исходник приложения, не выполняет HTTP,
не меняет auth и не управляет сервисом. Штатный owner installer передаёт ему
два уже проверенных массива bytes: bridge и frozen `nox-ui.js`.

```python
receipt = describe(current_bridge_bytes, frozen_ui_bytes)
candidate = transform(current_bridge_bytes, frozen_ui_bytes)
assert transform(candidate, frozen_ui_bytes, rollback=True) == current_bridge_bytes
```

Функция `transform` не имеет аргументов для ослабления source pins. При
любом несовпадении она выдаёт `PatchHold` до побочных эффектов установщика.
`_splice_tuple_bytes` — внутренний структурный примитив; установщик должен
вызывать только публичные `transform` / `describe`.

## Проверки кандидата

- Полный bridge preimage закреплён по SHA256 и длине.
- Frozen UI закреплён по `c5f6b23d…`; raw JS остаётся прежним.
- Вставляется только одна пара. Все остальные AST-узлы и исходные bytes
  должны совпасть. Сохраняются поздние chat/S03 изменения O1.
- Старый serving overlay обязан дать 42 933 байта / `18d8c8d6…`.
- Новый serving overlay обязан дать 43 021 байт /
  `13897495d7c9c628ef4f3094fafdad5f5932a3570d21c650112ba7138ab3c2f0`.
- Обратная подстановка JS должна точно вернуть прежний served JS.
- Rollback удаляет только эту вставку и обязан вернуть полный исходный
  bridge с SHA256 `17932e2f…`; посторонние изменения не затираются.

## Включение в существующую native транзакцию

Root/O1 владеет единственным dispatch. До записи требуется действующий
writer claim, штатный maintenance lock и актуальная защита owner chat. Старый
успешный canary не является текущим разрешением на остановку процесса.

Использовать существующие сохранение originals, compare-and-swap, атомарную
замену, fsync, health и rollback. Не применять исторический whole bridge,
не редактировать frozen JS, не добавлять новый daemon или scheduler.

Полный postSHA проверяется `describe` на том же проверенном native
preimage, а не на историческом локальном fixture. Перед записью установщик
повторно связывает SHA, inode и сервис с полученным планом. После существующего
согласованного reload проверяется точный served UI postSHA и прямой main URL.
Browser-клик и реальная генерация являются отдельными доказательствами.

**Зависимость O5:** его текущий `PROXY_PREREQUISITES` также закрепляет bridge
`17932e2f…`. Не устанавливать меню перед независимым O5 preflight без
согласованного обновления этого pin. Практические варианты: включить tuple
в уже запланированное общее offline окно с единым receipt, либо выполнить
меню после завершения текущего common/NORMAL3 cutover. Не повторять completed
canary run44177251374 ради меню.

## Проверено локально

`python -m unittest -v test_native_menu_overlay_transform.py`: **7/7 PASS**.
Структурная вставка дала byte-for-byte ранее reviewed historical candidate;
проверены strict fixed-entry rejection исторического файла, rollback,
неизменность frozen JS, чужие изменения, layout drift и UTF-8 byte offsets.

Для проверки общей логики roundtrip тесты временно подменяют pins **внутри
процесса теста** на известный historical fixture. Production constants
остаются actual17932…→9d747… . Затем отдельно выполнен production forward и
симметричный rollback на полном O1 source с тем же SHA, что installed bridge:
оба PASS, `CURRENT_INPUT_RECEIPT.json`. Это снимает прежний local input gap;
native install и served-after пока не заявляются как выполненные.

## Read-only проверка имени модели

`model_identity_projection.py` и `MODEL_IDENTITY_READSET.md` задают следующую
узкую проверку существующего status/backend/процесса без запроса генерации.
Проверены пять точных source pins, шесть исходных focused cases и один новый
regression с тремя подслучаями после независимого review argv-парсинга.
`INDEPENDENT_MODEL_REVIEW.json` фиксирует принятый final source. Его проекции
не заявляют listener/PID binding или содержимое весов доказанными: эти
свидетельства должен получить существующий native audit.
