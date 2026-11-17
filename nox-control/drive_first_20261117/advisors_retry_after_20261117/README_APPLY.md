# NOX advisors: точная дельта Retry-After

Это source patch к существующему каноническому пакету советников. Полный пакет, другой runtime и новый диспетчер здесь не публикуются.

## База и изменение

Канонический upstream: [NOX_ONLINE_ADVISORS_CORE_20261117.zip](https://drive.google.com/file/d/1WW8njIE1-NdmXcgPAPiK7iLlS0yJw5vQ/view).

- ZIP SHA256: `b7b11c008af64dbfcbef498bfa506b12dc527a853547e86f3f3ff2687bf4bc0e`.
- Корень внутри ZIP: `nox-online-advisors/`.
- До: `nox_advisors/client.py`, SHA256 `816cab725f99050ca8e4760712477dce6121c4c9b66482c47ac27f0ea7773ecf`.
- После: SHA256 `dc12679270d735507fb26613a679ee074f53c08aff8d72d28717196711cf2a54`.
- Reviewed local commit: `4a0317f8c66db5ae231ec50c6cb39869d000f98c`.

Конечный провайдерский `Retry-After` больше не сокращается до 300 секунд. Если интервал не помещается в deadline worker, существующий `consult()` сразу возвращает `RATE_LIMITED` и полный hint. Изменяется только `client.retry_delay`; правила free-only admission, callbacks host и deadline не меняются.

## Минимальная дельта для существующего client

`CLIENT_RUNTIME_ONLY.patch` — 1039 байт, SHA256 `ddb5789a4062bfd21bd63251756f79a392441fd402c066348c11fc6dd94baa75`. Он касается исключительно `nox_advisors/client.py` и имеет те же preimage/postimage SHA, что указаны выше. `git apply --check` и применение в одноразовой распаковке точного ZIP прошли; изменился ровно один файл, итоговый SHA совпал. Существующий installer может использовать этот файл после своей обычной проверки preimage и прав записи.

Полный reviewed `ADVISORS_RETRY_AFTER.patch` — 12440 байт — дополнительно содержит README, manifest, regression и сведения о квотах. Он также прошёл `git apply --check` на каноническом ZIP. Выберите один вариант дельты client; последовательное применение обоих патчей не требуется.

## Применение к существующей source-базе

1. Проверьте SHA канонического ZIP и подготовьте его существующую source-базу для изменения. До применения сравните все preimage SHA из `PUBLICATION_MAP.json`; два добавляемых файла должны отсутствовать. Существующий работающий native host не является целью этого source-патча.
2. Выполните из корня этой source-базы `git apply --check` с абсолютным путём к `ADVISORS_RETRY_AFTER.patch`. При несовпадении остановите применение и сопоставьте уже принятые правки; не используйте fuzz/force.
3. Примените тот же patch через `git apply` и проверьте postimage SHA из map. Patch уже включает regression и файл сведений о квотах; отдельная копия теста в публикации служит для review, её не нужно добавлять повторно.
4. Выполните целевую проверку:

```bash
PYTHONPATH=tests python -m unittest test_retry_after_contract test_advisors.TransportTests.test_429_backoff_same_model_no_fallback -v
```

Результат автора: 4/4 PASS. Независимый review проверил отдельно максимальный конечный float и дальний HTTP-date через `consult(deadline=0.2)`: один synthetic POST, ноль wait, конечный JSON. Полный baseline suite повторно не заявляется.

`SOURCE_RECEIPT.json` и manifest внутри frozen patch сохраняют авторское состояние до независимого review. Подтверждение последующего PASS для точного commit и client SHA — `INDEPENDENT_REVIEW_RECEIPT.json` и `PUBLICATION_MAP.json`; reviewed patch ради смены статуса не переписывался.

Существующие A2/O5 изменения `host.py` имеют собственную цепочку receipts и должны сохраниться при последующей интеграции. Этот patch не содержит `host.py`. Комплектный manifest описывает данную каноническую baseline-дельту; при объединении с другими source-патчами итоговый manifest пересчитывается по объединённым файлам.

Native binding, запуск provider API и состояние бесплатного аккаунта этой поставкой не подтверждаются. Provider API/native calls: 0. Auth, workflow и claim не изменялись. Ссылка на публикацию подтверждает сохранённый source, а не установку на сервер.
