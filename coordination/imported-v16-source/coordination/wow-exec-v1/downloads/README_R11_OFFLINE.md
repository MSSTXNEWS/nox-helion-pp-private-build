# NOX HELION EXPRESS INTEGRATOR · R11/MENU10 · локальные зависимости

Назначение: использовать **уже скачанные** проверенные ресурсы из блока 1, не выполнять Windows EXE, не переписывать существующий OneHost, не скачивать заново веса ИИ и не создавать второй рендерер. Это **исходный конфигуратор** для сборщика, а не релизный установщик.

## Фактический комплект

- WebView2 x64 Evergreen, Ollama Windows v0.40.13, NSIS 3.13 — **физические файлы и совпадение SHA-256**; проверка Authenticode проводится отдельно в Windows. Ни один EXE не выполняется конфигуратором.
- 16 NuGet-пакетов — отдельный SHA-pinned локальный feed. Версии не изменяются и пакеты не добавляются автоматически к WPF-проекту. Использовать только необходимые зависимости через существующий `.csproj`; WinUI runtime и SDK extensions не превращать в новую оболочку.
- LibreHardwareMonitorLib 0.9.6 — отдельно: SHA имеется, **NuGet signature HOLD**, пакет не входит в 16-пакетный разрешённый feed до независимой подписи.
- Fluent System Icons 6 SVG + MIT — размещаются локально для вторичного UI. Оригинальные HOME/MENU/CORE не заменяются; никаких файлов шрифтов в комплекте пользовательских выдач.
- Motion 14.9.0, tsParticles Engine/Slim 4.4.0, esbuild 0.28.2 — проверенный npm-архив; исходники инструментов кэшируются **без включения новых JS-движков** в текущий D02. Два одновременно активных 3D/particles рендера запрещены.
- kitUIN FluentIcon — скачанный WinUI-донор, не нужен WPF. Исходники остаются в архиве GitHub Actions, **не активируются**.
- оригинальная графика — берётся из утверждённой Drive папки FINISH_LOCK_ASSETS с исходными SHA; этот пакет не меняет изображения.

## Использование без сети и без Windows-установки

```bash
python configure_r11_offline.py \
  --cache /path/to/nox-r11-ready \
  --lock NOX_R11_DEPENDENCY_LOCK.json \
  --npm-archive /path/to/nox-r11-block1-source.zip \
  --out /path/to/isolated/NOX_R11_OFFLINE_DEPS
```

`--out` должен отсутствовать: это обеспечивает `NO-LOSS` исходных данных. Утилита сначала проверяет все 27 SHA и архив, затем атомарно формирует `nuget-feed` (16 файлов), `NuGet.Config`, `ui-fluent` (6 SVG + MIT), `npm-cache` (4 source module trees) и `R11_COMPONENT_RECEIPT.json`. Кэш npm не означает активацию Motion или tsParticles. Сгенерированный `NuGet.Config` используется **только** целевой сборкой и не меняет глобальные источники пакетов. Результат без исключений: `windows_installers_executed=false`, `installed_onehost=false`.

Без `--out` работает только read-only SHA-сверка. Отрицательные тесты: подмена файла, symlink, path traversal, повторное использование существующей выходной папки — запрет/NO-LOSS.

## Как подключается R11

Установленный исходный модуль уже подключён в PR #162 через `ui/onehost-menu-bindings.mjs` → `ui/nox-r11-wow.mjs`; его SHA фиксируется в `integrations/wow200/stage_wow200.py`, а Git blob stage в `coordination/e06/build_onehost_installer.ps1`. Нативные запросы используют **исключительно** существующий `createNativeMenuClient`. Инструмент offline-конфигурации является дополнением к этому пути, а не новым backend.

**Отдельные доказательства:** R11 JS тесты и Python конфигуратор не доказывают pixel-perfect всех сцен Drive, живую установленную GPU/AI-модель, native Windows E07 или настоящий релиз. Состояние этих требований остаётся HOLD, пока нет соответствующих receipt.
