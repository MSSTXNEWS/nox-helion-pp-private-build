# NOX V16 · Azure Windows CI · изолированный переход без потери исходников

**Статус:** конфигурация подготовлена на отдельной GitHub-ветке. Azure DevOps pipeline ещё НЕ создан и НЕ запускался. Это диагностический этап, а не подтверждение Windows E07.

## Точки привязки
- Репозиторий: `MSSTXNEWS/nox-helion-pp-private-build` (private).
- Исходный коммит, от которого ответвлена интеграция: `9706a488762725791be60db811a55d172631bac6`.
- Отдельная ветка: `ci/azure-nox-windows-r01-20261028`.
- Конфигурация: `azure-pipelines.yml` в корне. `trigger: none`, `pr: none` — только ручной запуск.
- Исходный PR #162, `main`, работа P01–P05, оригинальные `source_00/01/02.part`, D02, 8 CoreID, 5 Persona, WOW 1–200 и пользовательские данные не изменяются этой веткой.

## Подключение Azure DevOps (действия владельца)
1. В [Azure DevOps](https://dev.azure.com/) создать или выбрать **закрытый** проект и разрешить использование Microsoft-hosted Windows agent. Для бесплатных приватных parallel jobs нужна привязка Azure subscription/биллинга; само создание YAML бесплатно не запускает VM.
2. **Pipelines → New pipeline → GitHub**, авторизовать подключение к приватному репозиторию `MSSTXNEWS/nox-helion-pp-private-build`. Это разрешение на доступ к GitHub выдаёт владелец, не QA-исполнитель.
3. Выбрать YAML из ветки `ci/azure-nox-windows-r01-20261028`, путь `/azure-pipelines.yml`. Если Azure автоматически показывает `main`, выбрать именно отдельную ветку.
4. Проверить источник/ветку, запустить вручную. Проверить точный `Build.SourceVersion`, Azure BuildID и журналы всех шагов.
5. Скачать `nox-v16-azure-source-proof`. При успешной проверке оригинального SourceLock появится отдельная стадия диагностической Windows-сборки и `nox-v16-azure-windows-diagnostic-proof`.

## Что сохраняется и что проверяется
- Windows Server 2022; каждый job — новая VM; явный контроль `git rev-parse HEAD == Build.SourceVersion`.
- Повторно используются **существующие** `coordination/e06/verify_original_729_source.py`, `coordination/source-lock/verify_original_archive.py`, `private_build.ps1`, `coordination/e06/stage_p01.py` и `coordination/e06/build_onehost_installer.ps1`.
- Первым барьером служат 3 физических ZIP части, 729 фактических записей и их SHA-256, а также существующие E07 отрицательные тесты небезопасных ZIP.
- Только после успеха архива выполняется диагностический WPF/WebView2/NSIS build. В артефакты публикуются **receipts и SHA**, но не непроверенный исполняемый файл, модели, пользовательские данные или исходный архив.
- Продолжительность jobs ограничена 35 и 55 минутами соответственно. Azure hosted Windows VM не предоставляет CUDA GPU.

## Принципиальные ограничения
- Нынешний E06 builder явно помечен `ORIGINAL_PYTHON_READ_ONLY_DIAGNOSE`; нельзя представлять его как полнофункциональный ONEHOST релиз.
- `release_accepted=false`, `installed_exe_sha256=null`, `native_windows_e2e_passed=0` сохраняются до реальной независимой установки/приёмки.
- Перенос сборки с GitHub Actions на Azure **обходит проблему GitHub Billing/Spending Limit**, но не устраняет исходные проблемы продукта автоматически. Нужны реальный финальный Setup/EXE SHA и 10 E07 Windows E2E на одном установленном BuildID.
- Не включать автоматический merge в PR #162 и `main`; использовать owner receipt, pre/post SHA и single-writer ручного интегратора №1.

**RELEASE HOLD** до реального Windows исполнения и независимой приёмки.
