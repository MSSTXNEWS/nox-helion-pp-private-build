# NOX HELION · ПАТЧИ · КАТАЛОГ ПОСЛЕ RELEASE 1 · 2026-10-30

> **DEFERRED ONLY.** Это очередь возможных модулей, а НЕ установленный код или объявленные рабочими функции. До утверждённого Windows EXE, E07 PASS и SourceLock не создавать UI раздел, не устанавливать зависимости, не запускать серверы и не менять P01–P05.

**В текущем запуске:** единственный релизный приоритет — существующий OneHost и T06 Windows VM runner.

**Каталог существующего reuse-реестра:** [NOX MASTER READY SOLUTIONS V1.1](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/5f3e2216d5dc66e8df08ff8c5a4288d6df6e7ea5/coordination/catalogs/NOX_HELION_MASTER_READY_SOLUTIONS_V1_20261030.md).

**Проект будущего интерфейса:** MENU → **ПАТЧИ**: поиск, группировка, стоимость (free/paid/unknown), offline, лицензия, версия/размер, совместимость Windows/GPU, dependency chain, owner, permission/STOP, источник, точный SHA, кнопка «Посмотреть» и установка только после явного подтверждения владельца. Никаких подставных «установлено».

| Состояние | Значение |
|---|---|
| CANDIDATE | только URL и идея |
| REVIEW_REQUIRED | нужны лицензия/Windows/цена/безопасность |
| SOURCE_VERIFIED | определён безопасный исходный пакет |
| INSTALLED | реально установлено после релиза, есть receipt |
| ACCEPTED | независимое тестирование конкретного SHA |

## 8 семейств из текущего мастер-каталога · 116 источников

Прямые ссылки сохранены, **не скачаны и не развернуты**.

### WINDOWS_INSTALLER_P01 (12)

| Модуль | Зачем |
|---|---|
| [Microsoft WebView2 Samples](https://github.com/MicrosoftEdge/WebView2Samples) | WPF host HTML bridge |
| [WebView2 official documentation](https://learn.microsoft.com/microsoft-edge/webview2/) | profile/security |
| [NSIS](https://github.com/NSIS-Dev/nsis) | retain installer |
| [NSIS Modern UI 2](https://nsis.sourceforge.io/Docs/Modern%20UI%202/Readme.html) | wizard components |
| [CommunityToolkit.Mvvm](https://github.com/CommunityToolkit/dotnet) | WPF commands |
| [Microsoft.Extensions.Hosting](https://learn.microsoft.com/dotnet/core/extensions/generic-host) | DI/lifecycle |
| [WinGet CLI](https://github.com/microsoft/winget-cli) | permission-gated updater |
| [restic](https://github.com/restic/restic) | existing backup |
| [FlaUI](https://github.com/FlaUI/FlaUI) | installed Windows WPF E2E |
| [Pester](https://github.com/pester/Pester) | PowerShell tests |
| [PSScriptAnalyzer](https://github.com/PowerShell/PSScriptanalyzer) | build lint |
| [Velopack](https://github.com/velopack/velopack) | R2 comparison only |

### CINEMATIC_SHELL_PAGES (11)

| Модуль | Зачем |
|---|---|
| [Motion](https://github.com/motiondivision/motion) | approved animations |
| [GSAP](https://github.com/greensock/GSAP) | motion timelines, licence review |
| [OGL](https://github.com/oframe/ogl) | small WebGL |
| [Three.js](https://github.com/mrdoob/three.js) | optional existing 3D |
| [PixiJS](https://github.com/pixijs/pixijs) | 2D effects |
| [Lottie-web](https://github.com/airbnb/lottie-web) | approved animations |
| [Fluent UI System Icons](https://github.com/microsoft/fluentui-system-icons) | icons |
| [Lucide](https://github.com/lucide-icons/lucide) | icons |
| [Fuse.js](https://github.com/krisk/Fuse) | Ctrl+K search |
| [Floating UI](https://github.com/floating-ui/floating-ui) | overlay position |
| [Apache ECharts](https://github.com/apache/echarts) | real telemetry |

### LLM_MODEL_CENTER_P02_P03 (10)

| Модуль | Зачем |
|---|---|
| [Ollama](https://github.com/ollama/ollama) | single existing local LLM |
| [Ollama API](https://docs.ollama.com/api) | chat/tags/pull/embed |
| [OllamaSharp](https://github.com/awaescher/OllamaSharp) | .NET client optional |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | inference alternate, no second live host |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) | download by revision |
| [Transformers](https://github.com/huggingface/transformers) | model metadata |
| [safetensors](https://github.com/huggingface/safetensors) | safe weights |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | CPU/GPU optional |
| [ComfyUI](https://github.com/comfyanonymous/ComfyUI) | image workflow adapter |
| [Diffusers](https://github.com/huggingface/diffusers) | image models adapter |

### VOICE_CALLS_SOCIAL (14)

| Модуль | Зачем |
|---|---|
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) | offline ASR |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | ASR GPU candidate |
| [Silero VAD](https://github.com/snakers4/silero-vad) | VAD |
| [Piper](https://github.com/OHF-Voice/piper1-gpl) | TTS GPL compliance |
| [Kokoro](https://github.com/hexgrad/kokoro) | TTS candidate |
| [NAudio](https://github.com/naudio/NAudio) | Windows audio |
| [Marian NMT](https://github.com/marian-nmt/marian) | offline translation |
| [Argos Translate](https://github.com/argosopentech/argos-translate) | offline translation |
| [SIPSorcery](https://github.com/sipsorcery-org/sipsorcery) | SIP .NET |
| [PJSIP](https://github.com/pjsip/pjproject) | SIP alternate |
| [LiveKit](https://github.com/livekit/livekit) | realtime rooms; server/auth required |
| [Jitsi Meet](https://github.com/jitsi/jitsi-meet) | external/self-host meeting |
| [Matrix Synapse](https://github.com/element-hq/synapse) | social protocol, not R1 backend replacement |
| [Element Web](https://github.com/element-hq/element-web) | social UI reference, not full rebrand |

### RAG_GPU_LEARNING_P04 (15)

| Модуль | Зачем |
|---|---|
| [sentence-transformers](https://github.com/huggingface/sentence-transformers) | embeddings |
| [sqlite-vec](https://github.com/asg017/sqlite-vec) | SQLite vectors |
| [FAISS](https://github.com/facebookresearch/faiss) | vector index alternative |
| [LlamaIndex](https://github.com/run-llama/llama_index) | selective loaders |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | PDF AGPL/paid gate |
| [pypdf](https://github.com/py-pdf/pypdf) | PDF read |
| [Unstructured](https://github.com/Unstructured-IO/unstructured) | document extraction |
| [PEFT](https://github.com/huggingface/peft) | LoRA |
| [TRL](https://github.com/huggingface/trl) | training |
| [Accelerate](https://github.com/huggingface/accelerate) | training engine |
| [bitsandbytes](https://github.com/bitsandbytes-foundation/bitsandbytes) | GPU compatibility gate |
| [Axolotl](https://github.com/axolotl-ai-cloud/axolotl) | trainer configs |
| [Unsloth](https://github.com/unslothai/unsloth) | Windows/GPU gating |
| [pynvml](https://github.com/gpuopenanalytics/pynvml) | real GPU |
| [psutil](https://github.com/giampaolo/psutil) | real CPU/RAM |

### CREATIVE_STUDIO_VIDEO_3D_AUDIO (17)

| Модуль | Зачем |
|---|---|
| [Godot](https://github.com/godotengine/godot) | R1 playable game/AI NPC |
| [Godot demos](https://github.com/godotengine/godot-demo-projects) | starter game scenes and saves |
| [Blender](https://github.com/blender/blender) | 3D authoring |
| [Blender Studio](https://studio.blender.org/training/) | 3D animation reference |
| [Remotion](https://github.com/remotion-dev/remotion) | programmatic video; licence gate |
| [FFmpeg](https://github.com/FFmpeg/FFmpeg) | video processing GPL/LGPL gate |
| [OBS Studio](https://github.com/obsproject/obs-studio) | screen capture |
| [Audacity](https://github.com/audacity/audacity) | audio editing |
| [OpenCV](https://github.com/opencv/opencv) | vision |
| [Pillow](https://github.com/python-pillow/Pillow) | images |
| [ImageMagick](https://github.com/ImageMagick/ImageMagick) | images; policy limits |
| [Tesseract](https://github.com/tesseract-ocr/tesseract) | OCR |
| [Penpot](https://github.com/penpot/penpot) | design source/templates |
| [GIMP](https://gitlab.gnome.org/GNOME/gimp) | image authoring |
| [Krita](https://invent.kde.org/graphics/krita) | drawing |
| [LMMS](https://github.com/LMMS/lmms) | music authoring |
| [MuseScore](https://github.com/musescore/MuseScore) | score editor |

### WORK_OS_SITES_APPS_DATA (16)

| Модуль | Зачем |
|---|---|
| [Monaco Editor](https://github.com/microsoft/monaco-editor) | source editor |
| [CodeMirror](https://github.com/codemirror/dev) | lighter editor |
| [Vite](https://github.com/vitejs/vite) | web previews/build |
| [Astro](https://github.com/withastro/astro) | site templates |
| [Next.js](https://github.com/vercel/next.js) | web app templates; avoid 2nd production runtime by default |
| [Tauri](https://github.com/tauri-apps/tauri) | R2 compare, not new host |
| [DuckDB](https://github.com/duckdb/duckdb) | local analytics |
| [Apache Arrow](https://github.com/apache/arrow) | Parquet/Arrow |
| [Pandas](https://github.com/pandas-dev/pandas) | data analysis |
| [Plotly](https://github.com/plotly/plotly.py) | charts |
| [Pandoc](https://github.com/jgm/pandoc) | document conversion |
| [LibreOffice](https://www.libreoffice.org/) | office conversion external |
| [python-pptx](https://github.com/scanny/python-pptx) | slides |
| [python-docx](https://github.com/python-openxml/python-docx) | documents |
| [openpyxl](https://openpyxl.readthedocs.io/) | spreadsheets |
| [PDF.js](https://github.com/mozilla/pdf.js) | PDF view |

### CONNECTORS_AUTONOMY_SECURITY (21)

| Модуль | Зачем |
|---|---|
| [MCP specification](https://modelcontextprotocol.io/) | tool manifests |
| [MCP servers](https://github.com/modelcontextprotocol/servers) | reference adapters |
| [Microsoft Graph](https://learn.microsoft.com/graph/overview) | Outlook/calendar/contacts auth |
| [Gmail API](https://developers.google.com/workspace/gmail/api) | mail after OAuth |
| [Google Calendar API](https://developers.google.com/workspace/calendar/api) | calendar after OAuth |
| [GitHub REST](https://docs.github.com/rest) | repo-scoped tools |
| [Vercel API](https://vercel.com/docs/rest-api) | deploy after approval |
| [Railway API](https://docs.railway.com/reference/public-api) | deploy after approval |
| [n8n](https://github.com/n8n-io/n8n) | source-available licence check; R2 |
| [Temporal](https://github.com/temporalio/temporal) | durable job framework, too heavy for R1 |
| [Polly](https://github.com/App-vNext/Polly) | resilience |
| [Serilog](https://github.com/serilog/serilog) | logs |
| [OpenTelemetry .NET](https://github.com/open-telemetry/opentelemetry-dotnet) | traces |
| [Gitleaks](https://github.com/gitleaks/gitleaks) | secrets |
| [Syft](https://github.com/anchore/syft) | SBOM |
| [Grype](https://github.com/anchore/grype) | dependency security |
| [Cosign](https://github.com/sigstore/cosign) | artifact signatures |
| [Playwright](https://github.com/microsoft/playwright) | web QA |
| [pytest](https://github.com/pytest-dev/pytest) | Python QA |
| [xUnit](https://github.com/xunit/xunit) | C# QA |
| [GitLab Windows runner](https://docs.gitlab.com/ci/runners/hosted_runners/windows/) | source/build diagnostics |

## 9 дополнительных семейств · 50 кандидатов

Все эти решения **только идеи будущей адаптации**, отдельные движки и серверы могут быть избыточны. Включать после Release только при реальном функциональном запросе.

### BUILD_SECURITY (8)

| Решение | Зачем |
|---|---|
| [Trivy](https://github.com/aquasecurity/trivy) | сканирование контейнеров/файлов |
| [Ruff](https://github.com/astral-sh/ruff) | быстрая проверка Python |
| [uv](https://github.com/astral-sh/uv) | быстрая сборка Python окружений |
| [pre-commit](https://github.com/pre-commit/pre-commit) | адресные source hooks |
| [Renovate](https://github.com/renovatebot/renovate) | контроль обновлений зависимостей |
| [OSV-Scanner](https://github.com/google/osv-scanner) | проверка уязвимостей зависимостей |
| [CycloneDX](https://github.com/CycloneDX/cyclonedx-cli) | SBOM проверка и экспорт |
| [signtool](https://learn.microsoft.com/windows/win32/seccrypto/signtool) | проверка подписи релиза |

### BACKUP_SYNC (3)

| Решение | Зачем |
|---|---|
| [rclone](https://github.com/rclone/rclone) | резервное копирование и синхронизация |
| [Syncthing](https://github.com/syncthing/syncthing) | локальная синхронизация устройств |
| [Kopia](https://github.com/kopia/kopia) | снимки файлов и восстановление |

### LOCAL_STORAGE (4)

| Решение | Зачем |
|---|---|
| [LiteFS](https://github.com/superfly/litefs) | исследование безопасной репликации |
| [Qdrant](https://github.com/qdrant/qdrant) | внешний векторный индекс при необходимости |
| [Chroma](https://github.com/chroma-core/chroma) | RAG сравнение после Release |
| [DuckDB Extensions](https://duckdb.org/docs/stable/extensions/overview) | локальный SQL и внешние данные |

### MEDIA_DOCUMENTS (5)

| Решение | Зачем |
|---|---|
| [Docling](https://github.com/docling-project/docling) | извлечение структурированного текста |
| [Calibre](https://github.com/kovidgoyal/calibre) | книги и конверсия электронных книг |
| [markitdown](https://github.com/microsoft/markitdown) | офисные документы в Markdown |
| [LibreTranslate](https://github.com/LibreTranslate/LibreTranslate) | автономный перевод при необходимости |
| [GStreamer](https://gitlab.freedesktop.org/gstreamer/gstreamer) | медиа-конвейеры |

### OPS_MONITORING (6)

| Решение | Зачем |
|---|---|
| [Sentry](https://github.com/getsentry/sentry) | отчёты об ошибках с согласием |
| [Grafana](https://github.com/grafana/grafana) | операционная визуализация |
| [Prometheus](https://github.com/prometheus/prometheus) | сбор метрик |
| [Loki](https://github.com/grafana/loki) | структурированные логи |
| [Langfuse](https://github.com/langfuse/langfuse) | трассировка локальных ИИ-вызовов |
| [OpenObserve](https://github.com/openobserve/openobserve) | аналитика системных событий |

### CONNECTORS_WORK (8)

| Решение | Зачем |
|---|---|
| [NocoDB](https://github.com/nocodb/nocodb) | доступ к данным и таблицам |
| [Activepieces](https://github.com/activepieces/activepieces) | конструктор автоматизаций |
| [Node-RED](https://github.com/node-red/node-red) | визуальная маршрутизация интеграций |
| [Home Assistant](https://github.com/home-assistant/core) | локальные устройства и автоматизация |
| [Gitea](https://github.com/go-gitea/gitea) | локальный git сервер |
| [Forgejo](https://codeberg.org/forgejo/forgejo) | git хостинг альтернативный |
| [OpenAPI Generator](https://github.com/OpenAPITools/openapi-generator) | генерация контрактных API клиентов |
| [Spectral](https://github.com/stoplightio/spectral) | контрактная проверка OpenAPI |

### LOCAL_AGENT (5)

| Решение | Зачем |
|---|---|
| [Open WebUI](https://github.com/open-webui/open-webui) | UI reference для локального LLM |
| [LiteLLM](https://github.com/BerriAI/litellm) | опциональный шлюз моделей |
| [MCP Inspector](https://github.com/modelcontextprotocol/inspector) | тестирование MCP инструментов |
| [Ollama Model Library](https://ollama.com/library) | метаданные моделей |
| [ONNX Models](https://huggingface.co/onnx-community) | каталог компактных моделей |

### SECURITY_PRIVACY (5)

| Решение | Зачем |
|---|---|
| [OpenBao](https://github.com/openbao/openbao) | хранилище секретов |
| [Tailscale](https://github.com/tailscale/tailscale) | сетевое соединение устройств с согласием |
| [WireGuard](https://www.wireguard.com/) | защищённые туннели |
| [Keycloak](https://github.com/keycloak/keycloak) | отдельная авторизация в будущем |
| [Caddy](https://github.com/caddyserver/caddy) | HTTPS для будущих сервисов |

### TESTING (6)

| Решение | Зачем |
|---|---|
| [Pact](https://github.com/pact-foundation/pact-js) | контрактные тесты |
| [Vitest](https://github.com/vitest-dev/vitest) | тесты HTML JS |
| [Cypress](https://github.com/cypress-io/cypress) | веб-регрессия |
| [GitHub Actions Runner](https://github.com/actions/runner) | резервный CI исполнитель |
| [GitLab Runner](https://gitlab.com/gitlab-org/gitlab-runner) | собственный Windows CI |
| [WinAppDriver](https://github.com/microsoft/WinAppDriver) | Windows GUI испытания |

## Гейт после выпуска

1. Подписанный OWNER release и независимая E07 принятие на одном SHA.
2. Одна новая функция за раз, сначала reuse существующей библиотеки.
3. Для каждого кандидата перед интеграцией проверять официальный upstream, точные версии, лицензии, риск GPL/AGPL, CVD/подпись, права и необходимость внешнего сервера.
4. Не добавлять альтернативные движки ради количества; утверждённые HOME/MENU/WORK и персоны — неизменяемые source assets.
5. Все новые зависимости только после отдельного owner consent, с возможностью удаления и rollback.

ИТОГО: 116 готовых ссылок реестра + 50 дополнительных кандидатов = **166 решений**, **0 установлено этим изменением**.

Status: POST_RELEASE_BACKLOG_NOT_PRODUCT_PROGRESS.
