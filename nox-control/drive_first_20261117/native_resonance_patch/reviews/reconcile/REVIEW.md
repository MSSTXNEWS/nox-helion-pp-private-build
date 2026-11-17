# Read-only reconciliation: независимая проверка

**PASS source review; concrete blockers не обнаружены. Native PASS не заявлен.** Проверенный source SHA: `7b82ccbb235bd51c9a4782919aa6cfd484ad96e253ef0c2cebd9c61ca8e2ef9e`.

Назначенный вызов: `run(False, expected_source_sha=source, reconcile_dialog_id=RECONCILE_DIALOG_ID)`. Фиксированный own dialog: `5ce69137da0a4c42a0387917c8567d52`. Это не повтор canary.

Три независимых fixtures PASS. Использован реальный transport gate `LoopbackClient` с fake opener, без сети. Положительный readback выполняет только официальный login и разрешённые GET. И успешный результат, и malformed HTTP503/history JSON, и transport timeout оставляют `model_requests=0`, `dialogs_created=0`; STOP и повторная генерация отсутствуют. Другой ID, неправильный owner_ui pin, create/stream/STOP даже без POST data запрещены до transport.

Compound HTML принимается лишь по exact SHA/размеру с подтверждённым pin owner_chat_ui; общий очиститель/обход hash отсутствует. `reconciliation_pass=true` не меняет `native_canary_pass=false`: потерянные terminal flags/S03 receipt/timings не восстанавливаются догадкой. Приватные body/header/exception/cookie/password/exchange sentinels не попадают в результат.

Native сервер и внешний tunnel reviewer не вызывал. Root должен использовать именно read-only wrapper и действующие owner-operator проверки. NEXT_READY — публикация этих bytes и одна допущенная read-only проверка фиксированного диалога; модель не вызывать. Review claim освобождён.
