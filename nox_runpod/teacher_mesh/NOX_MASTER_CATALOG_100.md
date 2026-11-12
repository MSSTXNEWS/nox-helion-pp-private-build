# NOX HELION — общий мастер-каталог: 100 готовых компонентов + 15 моделей + 20 червей

Источник: [NOX GitHub PR #251](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/251) · [архив программы NOX36](https://drive.google.com/file/d/10u1_U4JKXNTCQEIvgnhVrWufHj5fBgFk/view) · [черви на Drive](https://drive.google.com/file/d/1MLWJqDIYrgvN4PUxfunubkw0toZe6Pkl/view).

> Каталог кандидатов, а не подтверждение скачивания/инсталляции. Версии и лицензии каждого проекта проверять перед применением. Все новые зависимости опциональны; S03 и текущий backend не заменять. Модели-учителя на отдельной VM; NOX обучается только на проверенных ответах, не на чужих весах.

## 100 компонентов

### 01 · Учителя / нейронка / качество / S03 / FORGE

| № | Инструмент | Зачем NOX | Источник |
|---:|---|---|---|
| 1 | vLLM | Скоростная VM-инференция | [скачать / исходник](https://github.com/vllm-project/vllm) |
| 2 | SGLang | Быстрый MoE-сервер | [скачать / исходник](https://github.com/sgl-project/sglang) |
| 3 | llama.cpp | GGUF на небольших GPU/CPU | [скачать / исходник](https://github.com/ggml-org/llama.cpp) |
| 4 | Ollama | Простая локальная библиотека моделей | [скачать / исходник](https://github.com/ollama/ollama) |
| 5 | LiteLLM | Единый адаптер API и fallback | [скачать / исходник](https://github.com/BerriAI/litellm) |
| 6 | OpenRouter Free | Резерв бесплатных облачных ответов | [скачать / исходник](https://openrouter.ai/collections/free-models) |
| 7 | huggingface_hub | Скачивание моделей с SHA и версиями | [скачать / исходник](https://github.com/huggingface/huggingface_hub) |
| 8 | HF Datasets | Потоковая загрузка проверенных датасетов | [скачать / исходник](https://github.com/huggingface/datasets) |
| 9 | DataTrove | ETL и чистка корпусов | [скачать / исходник](https://github.com/huggingface/datatrove) |
| 10 | Argilla | Разметка хороших/плохих ответов | [скачать / исходник](https://github.com/argilla-io/argilla) |
| 11 | Transformers | Фундаментальный нейронный тренер | [скачать / исходник](https://github.com/huggingface/transformers) |
| 12 | PEFT LoRA / rsLoRA / DoRA | Адаптерная грибница разных слоёв | [скачать / исходник](https://github.com/huggingface/peft) |
| 13 | TRL | Response-only SFT и DPO | [скачать / исходник](https://github.com/huggingface/trl) |
| 14 | Unsloth | Оптимизированные training kernels | [скачать / исходник](https://github.com/unslothai/unsloth) |
| 15 | Axolotl | Воспроизводимые рецепты и конфиги | [скачать / исходник](https://github.com/axolotl-ai-cloud/axolotl) |
| 16 | Liger Kernel | Fused loss и Triton kernels | [скачать / исходник](https://github.com/linkedin/Liger-Kernel) |
| 17 | bitsandbytes | 8-bit оптимизаторы | [скачать / исходник](https://github.com/bitsandbytes-foundation/bitsandbytes) |
| 18 | FlashAttention | Проверенная быстрая attention | [скачать / исходник](https://github.com/Dao-AILab/flash-attention) |
| 19 | Accelerate | Запуск на нескольких устройствах | [скачать / исходник](https://github.com/huggingface/accelerate) |
| 20 | DeepSpeed | ZeRO и управление памятью | [скачать / исходник](https://github.com/deepspeedai/DeepSpeed) |
| 21 | lm-evaluation-harness | Независимые тесты знаний/кода | [скачать / исходник](https://github.com/EleutherAI/lm-evaluation-harness) |
| 22 | LightEval | Лёгкие скоростные eval | [скачать / исходник](https://github.com/huggingface/lighteval) |
| 23 | RAGAS | Проверка ответа с контекстом RAG | [скачать / исходник](https://github.com/explodinggradients/ragas) |
| 24 | RewardBench | Проверка reward-модели | [скачать / исходник](https://github.com/allenai/reward-bench) |
| 25 | AlpacaEval | Парное сравнение ответов | [скачать / исходник](https://github.com/tatsu-lab/alpaca_eval) |
| 26 | Giskard OSS | Тесты ошибок и рисков агентов | [скачать / исходник](https://github.com/Giskard-AI/giskard-oss) |
| 27 | datasketch | Дедупликация схожих ответов | [скачать / исходник](https://github.com/ekzhu/datasketch) |
| 28 | Outlines | Структурированный JSON-ответ | [скачать / исходник](https://github.com/dottxt-ai/outlines) |
| 29 | Instructor | Валидация схем и инструментов | [скачать / исходник](https://github.com/567-labs/instructor) |
| 30 | Optuna | Автоподбор гиперпараметров | [скачать / исходник](https://github.com/optuna/optuna) |
| 31 | sqlite-vec | Векторный поиск внутри S03 SQLite | [скачать / исходник](https://github.com/asg017/sqlite-vec) |
| 32 | Qwen3 Embedding 0.6B | Эмбеддинги RU/ES/EN для S03 | [скачать / исходник](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) |
| 33 | Qwen3 Reranker 0.6B | Ранжирование найденной памяти | [скачать / исходник](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) |
| 34 | LlamaIndex | RAG по файлам и внешним знаниям | [скачать / исходник](https://github.com/run-llama/llama_index) |
| 35 | Haystack | Гибридные поисковые пайплайны | [скачать / исходник](https://github.com/deepset-ai/haystack) |
| 36 | LangGraph | Граф задач с долгим состоянием | [скачать / исходник](https://github.com/langchain-ai/langgraph) |
| 37 | smolagents | Разрешённые инструменты автономных агентов | [скачать / исходник](https://github.com/huggingface/smolagents) |
| 38 | APScheduler | Отложенные локальные задачи | [скачать / исходник](https://github.com/agronholm/apscheduler) |
| 39 | Temporal | Устойчивые долгие задания и retries | [скачать / исходник](https://github.com/temporalio/temporal) |
| 40 | n8n | Визуальные интеграции сервисов | [скачать / исходник](https://github.com/n8n-io/n8n) |
| 41 | OpenHands | Самодоработка кода в sandbox | [скачать / исходник](https://github.com/OpenHands/OpenHands) |
| 42 | Aider | Git-патчи из диалога | [скачать / исходник](https://github.com/Aider-AI/aider) |
| 43 | pytest | Регрессионные тесты кода | [скачать / исходник](https://github.com/pytest-dev/pytest) |
| 44 | Playwright | UI-тесты Резонанса и Windows WebView | [скачать / исходник](https://github.com/microsoft/playwright) |
| 45 | Ruff | Быстрая проверка и исправление Python | [скачать / исходник](https://github.com/astral-sh/ruff) |
| 46 | Docker Engine | Изоляция учителей и исполняемого кода | [скачать / исходник](https://docs.docker.com/engine/install/) |
| 47 | FastAPI | Схема инструментов существующего backend | [скачать / исходник](https://github.com/fastapi/fastapi) |
| 48 | Prometheus | Правдивая GPU/CPU/step-телеметрия | [скачать / исходник](https://github.com/prometheus/prometheus) |
| 49 | faster-whisper | Распознавание RU/ES речи | [скачать / исходник](https://github.com/SYSTRAN/faster-whisper) |
| 50 | Piper TTS | Локальный голос RU/ES | [скачать / исходник](https://github.com/OHF-Voice/piper1-gpl) |

### 02 · Web / UI / браузер

| № | Инструмент | Зачем NOX | Источник |
|---:|---|---|---|
| 51 | Browser Use | Браузерный агент с локальной моделью | [скачать / исходник](https://github.com/browser-use/browser-use) |
| 52 | Playwright MCP | Управление браузером через MCP | [скачать / исходник](https://github.com/microsoft/playwright-mcp) |
| 53 | Chrome DevTools MCP | DevTools: ошибки, память, сеть, производительность | [скачать / исходник](https://github.com/ChromeDevTools/chrome-devtools-mcp) |
| 54 | Stagehand | Устойчивые DOM-действия и извлечение | [скачать / исходник](https://github.com/browserbase/stagehand) |
| 55 | Crawl4AI | Сбор открытых веб-страниц для RAG | [скачать / исходник](https://github.com/unclecode/crawl4ai) |
| 56 | Vite | Быстрая сборка веб-интерфейса | [скачать / исходник](https://github.com/vitejs/vite) |
| 57 | Astro | Лёгкие сайты и документация | [скачать / исходник](https://github.com/withastro/astro) |
| 58 | SvelteKit | Компонентные веб-приложения | [скачать / исходник](https://github.com/sveltejs/kit) |
| 59 | Three.js | Кинематографичные 3D-сцены D02 | [скачать / исходник](https://github.com/mrdoob/three.js) |
| 60 | GSAP | Временные линии анимации WOW | [скачать / исходник](https://github.com/greensock/GSAP) |
| 61 | Apache ECharts | Сложные графики CPU/GPU/VRAM | [скачать / исходник](https://github.com/apache/echarts) |
| 62 | Storybook | Каталог и визуальная проверка кнопок | [скачать / исходник](https://github.com/storybookjs/storybook) |
| 63 | Vitest | Быстрые локальные JS-тесты | [скачать / исходник](https://github.com/vitest-dev/vitest) |
| 64 | Biome | Единое форматирование и линтинг веб | [скачать / исходник](https://github.com/biomejs/biome) |
| 65 | Lit | Компоненты без замены текущего backend | [скачать / исходник](https://github.com/lit/lit) |
| 66 | Tailwind CSS | CSS-шаблоны интерфейса | [скачать / исходник](https://github.com/tailwindlabs/tailwindcss) |

### 03 · Когнитивная надстройка

| № | Инструмент | Зачем NOX | Источник |
|---:|---|---|---|
| 67 | LangMem | memory_extraction — S03 function-only integration; do not replace store | [скачать / исходник](https://github.com/langchain-ai/langmem) |
| 68 | Mem0 | memory_significance — Study recall scoring; external storage disabled | [скачать / исходник](https://github.com/mem0ai/mem0) |
| 69 | Graphiti | temporal_knowledge — Study temporal fact edges + source/time in S03, no Neo4j on production | [скачать / исходник](https://github.com/getzep/graphiti) |
| 70 | Hindsight | autobiographical_memory — Study episodic memories, observation and mental models, no second DB | [скачать / исходник](https://github.com/vectorize-io/hindsight) |
| 71 | Letta Code | identity_lifecycle — Study persistent agent identity and episodic memory; no replacement runtime | [скачать / исходник](https://github.com/letta-ai/letta-code) |
| 72 | Cognee | semantic_graph — Optional isolated pilot; do not fork canonical S03 | [скачать / исходник](https://github.com/topoteretes/cognee) |
| 73 | HippoRAG 2 | associative_retrieval — Benchmark on source-attributed S03 retrieval against sqlite-vec | [скачать / исходник](https://github.com/OSU-NLP-Group/HippoRAG) |
| 74 | Generative Agents | reflection_planning — Research memory importance and planning, not genuine consciousness | [скачать / исходник](https://github.com/joonspk-research/generative_agents) |
| 75 | OpenPsi Hyperon | cognitive_appraisal — Experimental motivations and feeling updater; no independent 'needs' claims | [скачать / исходник](https://github.com/iCog-Labs-Dev/hyperon-openpsi) |
| 76 | DSPy | quality_optimizer — Improve prompt/program via independent eval, only propose new weights separately | [скачать / исходник](https://github.com/stanfordnlp/dspy) |
| 77 | ruBERT CEDR Emotion | emotion_ru — Local text emotion classification; output is uncertain observation, not diagnosis | [скачать / исходник](https://huggingface.co/cointegrated/rubert-tiny2-cedr-emotion-detection) |
| 78 | MarIA Emotion ES | emotion_es — Separate local Spanish classifier; compare label mappings and licenses | [скачать / исходник](https://huggingface.co/UMUTeam/MarIA-emotion-es) |
| 79 | MemOS | memory_skills — Study memory cubes/skill traces; no duplicate canonical DB | [скачать / исходник](https://github.com/MemTensor/MemOS) |
| 80 | LightRAG | graph_rag — Optional isolated indexer; no public API; S03 remains master | [скачать / исходник](https://github.com/HKUDS/LightRAG) |
| 81 | Memory Agent Benchmarks | memory_evaluation — Measure LoCoMo/LongMemEval end-to-end before replacing retrieval | [скачать / исходник](https://github.com/RonsenbergVI/agent-memory-benchmarks) |
| 82 | Aniemore | emotion_voice_ru — Optional local acoustic emotion; opt-in only; no mood diagnosis | [скачать / исходник](https://github.com/aniemore/Aniemore) |
| 83 | Microsoft GraphRAG | knowledge_graph_research — Research-only, maintainer says maintenance mode and costly indexing | [скачать / исходник](https://github.com/microsoft/graphrag) |

### 04 · Черви / отказоустойчивость / мини-инструменты

| № | Инструмент | Зачем NOX | Источник |
|---:|---|---|---|
| 84 | Huey | долговечная очередь задач на SQLite, переживает перезагрузку | [скачать / исходник](https://github.com/coleifer/huey) |
| 85 | watchdog | слежка за папками: новый файл -> задача индексации | [скачать / исходник](https://github.com/gorakhargosh/watchdog) |
| 86 | GitPython | локальный git: ветки, коммиты, diff, откат собственных правок (push запрещён) | [скачать / исходник](https://github.com/gitpython-developers/GitPython) |
| 87 | whatthepatch | разбор и наложение unified diff в памяти, до теста ничего не пишет | [скачать / исходник](https://github.com/cscorley/whatthepatch) |
| 88 | RestrictedPython | выполнение расчётов без import/open/сети | [скачать / исходник](https://github.com/zopefoundation/RestrictedPython) |
| 89 | ollama-python | вызов функций моделью NOX, диспетчер tool_calls с проверкой | [скачать / исходник](https://github.com/ollama/ollama-python) |
| 90 | json-repair | чинит битый JSON из ответов модели | [скачать / исходник](https://github.com/mangiucugna/json_repair) |
| 91 | pydantic | строгая проверка аргументов инструментов | [скачать / исходник](https://github.com/pydantic/pydantic) |
| 92 | MCP Python SDK | NOX как MCP-сервер (stdio, локально) | [скачать / исходник](https://github.com/modelcontextprotocol/python-sdk) |
| 93 | trafilatura | чистый текст статьи без меню и рекламы | [скачать / исходник](https://github.com/adbar/trafilatura) |
| 94 | Scrapling | быстрый разбор CSS/XPath, адаптивные селекторы | [скачать / исходник](https://github.com/D4Vinci/Scrapling) |
| 95 | pypdf | текст PDF без GPU | [скачать / исходник](https://github.com/py-pdf/pypdf) |
| 96 | rank_bm25 | BM25 рядом с векторами bge-m3 | [скачать / исходник](https://github.com/dorianbrown/rank_bm25) |
| 97 | FlashRank | переранжирование фрагментов на CPU (ONNX) | [скачать / исходник](https://github.com/PrithivirajDamodaran/FlashRank) |
| 98 | NetworkX | связи воспоминаний/добычи, JSON для 3D-страницы | [скачать / исходник](https://github.com/networkx/networkx) |
| 99 | psutil | CPU/RAM/диск/процессы для раздела «Обучение» | [скачать / исходник](https://github.com/giampaolo/psutil) |
| 100 | nvidia-ml-py (NVML) | температура/загрузка NVIDIA на внешней машине; на домашнем AMD — HOLD | [скачать / исходник](https://pypi.org/project/nvidia-ml-py/) |

## 15 моделей-учителей

| № | Модель | Карточка / веса |
|---:|---|---|
| 1 | Qwen3.5 4B | [Hugging Face](https://huggingface.co/Qwen/Qwen3.5-4B) |
| 2 | Qwen3.5 9B | [Hugging Face](https://huggingface.co/Qwen/Qwen3.5-9B) |
| 3 | Qwen3.5 27B | [Hugging Face](https://huggingface.co/Qwen/Qwen3.5-27B) |
| 4 | Qwen3.5 35B-A3B | [Hugging Face](https://huggingface.co/Qwen/Qwen3.5-35B-A3B) |
| 5 | Qwen3 8B | [Hugging Face](https://huggingface.co/Qwen/Qwen3-8B) |
| 6 | Qwen3 32B | [Hugging Face](https://huggingface.co/Qwen/Qwen3-32B) |
| 7 | Qwen3 Coder 30B-A3B | [Hugging Face](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct) |
| 8 | DeepSeek R1 Distill Qwen 32B | [Hugging Face](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B) |
| 9 | gpt-oss 20B | [Hugging Face](https://huggingface.co/openai/gpt-oss-20b) |
| 10 | gpt-oss 120B | [Hugging Face](https://huggingface.co/openai/gpt-oss-120b) |
| 11 | Phi-4 | [Hugging Face](https://huggingface.co/microsoft/phi-4) |
| 12 | Mistral Small 3.1 24B | [Hugging Face](https://huggingface.co/mistralai/Mistral-Small-3.1-24B-Instruct-2503) |
| 13 | GLM 4.5 Air | [Hugging Face](https://huggingface.co/zai-org/GLM-4.5-Air) |
| 14 | GLM 4.6 | [Hugging Face](https://huggingface.co/zai-org/GLM-4.6) |
| 15 | Gemma 4 26B A4B | [Hugging Face](https://huggingface.co/google/gemma-4-26B-A4B-it) |

## 20 типов червей

| № | Название | Функция |
|---:|---|---|
| 1 | Worm Providers | Official registered provider adapters |
| 2 | WormAutopilot | Owner-approved native idle/boot tick |
| 3 | WormSwarm | Bounded parallel work queues and STOP-aware checks |
| 4 | NativeIdeaLoop | Local idea/research proposal generation |
| 5 | A1InitiativeBridge | S03 lessons and curated daily discovery |
| 6 | FORGE Candidate | Propose reversible code changes for owner review |
| 7 | Predator Teacher Hunt | Teacher search, trust/license gates, NOX-only training |
| 8 | GitHub API Worm | Source and package metadata through official API |
| 9 | RSS/Atom Worm | Approved low-cost feed monitoring |
| 10 | YouTube Metadata Worm | Official public metadata, quota-controlled; optional |
| 11 | Registry Worm | PyPI/npm/NuGet official package discovery |
| 12 | Ollama Registry Worm | Discover model metadata, no automatic install |
| 13 | GitLab Worm | Connector-scoped GitLab discovery |
| 14 | Crawl4AI Worm | Allowed webpage collection with budget |
| 15 | Trafilatura Worm | Small RSS/article text extraction |
| 16 | Playwright Worker | Dynamic allowed page retrieval in sandbox |
| 17 | TikTok Research Worm | HOLD until eligibility approval |
| 18 | Hugging Face Teacher Hunt | Model/license/size evaluation |
| 19 | Source Validators / Quota Manager | github_scanner, feed_reader, quota_manager, source_validator |
| 20 | Local Intake | Local data/model discovery with hashes |

## Правила запуска

1. Проверить STOP/ACL, происхождение кода, лицензию, контрольную сумму и ресурсы VM.
2. Скачать только утверждённые пакеты. Сначала самый быстрый полезный стек, а не все 100.
3. Для NOX: реальный checkpoint и optimizer step, независимые оценки, rolling backup, no-loss.
4. Черви живут в существующем диспетчере, имеют TTL, квоты, fail-closed STOP, не размножаются.
5. Долгосрочная память только S03; самосознание — доказуемая функциональная SELF-MODEL, не субъективное утверждение.
6. Исходная программа NOX36/архив на Google Drive не меняются этим каталогом автоматически.


## Исправление отбора учителей — V2 (12.11.2026)

**Не устанавливать все 15.** Это каталог кандидатов, а не перечень обязательных загрузок. Два больших учителя из одной модельной семьи не гарантируют независимых знаний. Перед загрузкой проверить текущие веса, хэши, S03, прогресс обучения и физическое наличие учителей на VM. Дистилляция подтверждается только шагами оптимизатора, новой контрольной суммой checkpoint и независимой оценкой до/после.

| Класс | Кандидаты | Почему | Решение |
|---|---|---|---|
| CORE (к проверке) | Qwen3.5 27B; DeepSeek-R1-Distill-Qwen-32B; Qwen3-Coder-30B-A3B | Общие языки/знания; математическая проверка; программирование | Тестировать по одному на отдельных задачах, без безусловной установки |
| SPECIALIST (по пробелу) | Mistral Small 3.1; gpt-oss-20b; Gemma 4 26B-A4B | Межсемейная RU/ES-проверка; tools/planning; потенциальное зрение | Только при доказанной новой полезной способности; зрение проверить на реальном image input |
| EXISTING ASSET AUDIT | Qwen3 8B | Возможно уже является активным или историческим активом NOX | Сначала физическая инвентаризация и SHA; не загружать копию |
| RESERVE | Qwen3.5 4B, 9B, 35B-A3B; Qwen3 32B; Phi-4; GLM 4.5 Air | Перекрытие основных компетенций; возможно полезны как более дешёвые или независимые контрольные модели | Не скачивать до сравнительного экзамена |
| HOLD RESOURCE | gpt-oss-120b; GLM 4.6 | Высокие требования к памяти/бюджету; возможное пересечение с выбранными ролями | Не запускать без отдельного расчёта ресурсов и прироста |

**Функция отбора:** компетенция, которую NOX пока не демонстрирует → поиск уже имеющегося подходящего учителя → тест на непересекающихся заданиях → лицензия/стоимость/GPU → одна разрешённая загрузка → отбор проверенных ответов → отдельная дистилляция → независимый экзамен NOX → откат при NO_GAIN. При сомнении — HOLD, а не фальшивый PASS.

**Чего не делать:** не принимать 15 моделей за 15 источников независимого знания; не объявлять «поглощение весов» при простом сравнении ответов; не создавать вторую S03; не менять active_student или production; не смешивать чужие данные и разрешения с текущим обучением.


## WOW efficiency V3 — no busywork, no slower NOX

The catalog is NOT a deployment. No live GPU trainer or production route was modified here. Change the scheduling policy first, then run physical A/B on the current student.

- **Chat:** one NOX response immediately; zero default teacher fanout; bounded S03 recall, optional reflection only when justified, never wait for VM teachers.
- **Choose skills, not model names:** measure a skill gap on blind, source-separated tasks and check existing model SHA and previous lesson coverage before any download.
- **Start with ONE suitable teacher:** only add a second if it contributes an independent family or a measurable disagreement requiring resolution. No automatic 3–5-model ensemble.
- **Dedup BEFORE paying GPU:** cluster near-identical prompts and outputs, reject license-unknown or unverifiable samples. Prefer novelty and independently verified answers.
- **Train real NOX weights separately:** teacher text is data, not weight absorption. Only optimizer steps, checkpoint hash, and independent post-train gains count as neural improvement.
- **S03:** single authoritative store; bounded targeted retrieval, provenance/conflict handling and recall invalidation; not a second database.
- **Worms:** event/idle-driven, strictly limited by TTL, owner approval, quota and fail-closed STOP. No scanning in circles, self-replication or installations based on search results.
- **FORGE:** real patch → real test → acceptance; no fabricated PASS or production writes before acceptance.
- **Measure WOW:** independent task success increase, zero critical regressions, fewer hallucinated self-history claims, code accepted by tests, time-to-first-token, and GPU-hours per verified improvement. If benefit is absent, cancel the proposed teacher or change and retain the last good NOX.

This architecture favors **fast user experience + selective background learning**, not constant model consultation. Runtime wiring and GPU benchmark remain pending physical acceptance.
