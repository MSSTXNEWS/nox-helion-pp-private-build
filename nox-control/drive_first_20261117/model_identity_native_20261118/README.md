# NOX: точная привязка имени модели к процессу и порту

Статус: **готовый исходный код и синтетические проверки; native audit ещё не выполнен**.
Публикацию и один запуск через существующий owner audit координирует root. Пакет
не изменяет уже выполненную проверку отмены и её frozen payload `6436a866…`.

## Что реально делает пакет

`native_model_identity_readback.py` связывает пять точных исходников маршрута,
дисковый статус, backend config, фиксированный процесс и его IPv4 listener.
`model_identity_projection.py` — неизменённый ранее проверенный модуль SHA
`cb22df37c3b716c44c7fb8ab1828e4b220706ae985583bcfdb5ea58d4d596e65`.

Нативная проверка ограничена процессом **PID 3266857 / start_ticks 172046662**,
его полными argv/exe/cwd hashes и UID 0. Свежий basis:
run `44187317953`, request `6962437325`, source
`781dada3e796a1a9bee7c49ae46a56feb8dcbf8a`; в этой квитанции backend явно
равен `127.0.0.1:8098`, а все пять source SHA совпали. Это основание для нового
read-only наблюдения, а не замена новой проверки процесса.

| Группа | Точное чтение | Публичный результат |
|---|---|---|
| Маршрут | `/root/nox/scripts/{chat_proxy.py,nox_v29_chat_bridge.py,common.py,agent_loop.py,owner_chat_stream.py}` | Проверенные SHA и file metadata; код не выводится |
| Статус | `/root/nox/status/status.json`, до 131072 байт | Только заранее заданные поля модели, тип/маскировка, basename и возраст дискового снимка |
| Backend | `/root/nox/config/backend.json`, до 65536 байт | Только host/port/model reference; сырой config не выводится |
| Процесс | `/proc/3266857/{stat,cmdline,status,exe,cwd}` | Фиксированные identity hashes, PID/start, безопасный basename; полные argv не выводятся |
| Сеть | `/proc/3266857/ns/net`, `/proc/self/ns/net`, `/proc/3266857/net/tcp`, до 512 fd links | Один IPv4 listener `8098`, его inode и fd, принадлежащие тому же PID; одинаковое network namespace |
| Readiness | **Один GET `http://127.0.0.1:8098/health`** | Проверенный исходниками readiness predicate, статус/длина/hash ответа; тело не выводится |
| Координация | Существующий `/root/nox/state/owner_maintenance.lock`, dev36/ino59886214 | Проверка старого inode и неблокирующая advisory lease; файл не создаётся |

Из аргументов выводится только GGUF basename под известным корнем
`/root/nox/models/`. Значение credential option, даже похожее на `--model=…`,
не становится именем модели. Прочие значения аргументов остаются скрытыми.

Файлы маршрута и backend повторно проверяются после чтения listener и health.
PID/start/argv/exe/cwd и socket/fd binding также проверяются повторно. Периодическое
обновление status.json не объявляется ошибкой: это самостоятельный стабильный
дисковый снимок с точным временем чтения. Весь результат явно не является
атомарным снимком сервера.

## Границы результата

Положительный `listener_model_reference_verified` означает: этот конкретный
слушающий процесс запущен с данным GGUF reference. Это полезный проверяемый факт
для самоописания NOX. Он не доказывает содержимое весов, модельную архитектуру,
обучение, доступный контекст, загрузку всех shards или backend прошлого ответа.
`weight_content_identity_verified`, `architecture_or_training_identity_verified`
и `last_chat_backend_identified` остаются false.

Readiness сообщается отдельно: неуспешный `/health` не превращается в доказательство
активности fallback. Порт 8085 и `/props` не опрашиваются; поддержка `/props` этим
источником не подтверждена. При другом configured port или `localhost` без
проверенного разрешения имени пакет возвращает конкретный HOLD. Неизвестный
процесс не разыскивается по всему серверу и не подставляется автоматически.

## Исполнение и ограничения

`model_identity_audit_entry.py` берёт только два публичных контекстных параметра
существующего operator: `NOX_OWNER_REQUEST_ID`, `NOX_OWNER_SOURCE_SHA`. Окружение
приложения, ключи, cookies, пароли и полные конфиги не читаются и не выводятся.
Доступ к модели — только health GET; POST, генерации, dialog creation, STOP,
перезапуски, записи на сервер и сбросы счётчиков отсутствуют.

Дисковые/proc чтения: максимум 2 MiB суммарно; один ответ health — максимум
65536 байт плюс один байт для обнаружения переполнения. TCP table ограничена
262144 байтами и 4096 строками. Health timeout не больше 0.8 секунды, redirects
не следуются, environment proxy не используется. Cooperative budget — 15 секунд,
жёсткий SIGALRM — 20 секунд, весь stdout с operator markers — не больше 32768 байт.

Builder создаёт один self-contained
`public_payload/nox-control/owner_native_audit.py` из трёх модулей с SHA guards.
Он только читает и упаковывает исходники; native код при build не запускается.
Entry использует существующие `NOX_MAINT_AUDIT`/`NOX_MAINT_AUDIT_COMPLETE` markers.
Private launcher sources и любые ключи в bundle не входят.

## Проверки

Пять целевых TempFS tests прошли: корректная process/socket/model reference;
отказ при другом владельце socket или namespace; отказ при нескольких listeners
или source SHA drift; отказ при неподтверждённом host/port; полный entry с уже
существующим lock и ограниченным stdout. HTTP заменён локальным fake, все proc
файлы синтетические, секреты вымышленные. Native вызовов и реальных health GET нет.

После независимого review root может опубликовать точный bundle через существующий
audit entry и выполнить один read-only запуск, согласовав его с текущим cutover.
Живое имя модели появится только из его проверенной квитанции.
