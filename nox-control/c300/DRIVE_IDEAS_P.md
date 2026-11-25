# Аудит Google Диска: П1–П16 (канон v5, приложения)

Источник: Drive, документ «NOX — КАНОН v5: ПРИЛОЖЕНИЯ П1–П16» (id 1pSLutoMpfvxrgllT_WiQFpUZ2P7yd-CM7RCeF3fDw5Q), 339 430 символов, изменён 2026-11-24. Только чтение.
Формат строки: идея/механика/порог/роль → источник «П№ → раздел».

## Часть 1 (символы 0–70 000)

- П1 → Правила → «Правило Создателя 24.11: максимум готового — кода, ответов, диалогов; дистилляция и своё обучение — потом».
- П1 → Правила → лицензии разрешены Создателем, включая NC, «только для себя, без продажи».
- П1 → Правила → «Ставить и подключать сразу, непрерывно».
- П1 → Неизменно → три запрета: несовершеннолетние, реальные люди без согласия, нелегальное.
- П1 → Неизменно → STOP; бэкап перед каждой правкой живого контура; диск ≥ 15 ГБ; VRAM ≤ 92%; чат первым; запись в ops_changes.log с командой отката.
- П1 → таблица 20 систем → №1 Тело: nvidia-ml-py, psutil, prometheus-client; сенсориум 130 сигналов из ADD_SENSORIUM.md → mind/body.
- П1 → №2 Чувства: реестр по таблице сенсориума; py-trees/transitions → mind/senses.
- П1 → №3 Эмоции: текст RU (rubert-tiny2-cedr, ruRoberta go-emotions); голос DUSHA; эмо-векторы repeng, llama.cpp cvector; данные ESConv, EmpatheticDialogues, Toloka Persona, DUSHA → mind/emotion.
- П1 → №4 Разум: langgraph, dspy, outlines/xgrammar, litellm (консилиум); ToM-наборы ToMi, FANToM, OpenToM для теста → mind/reason.
- П1 → №5 Самоосознание: persona_vectors, repeng; lrudl/sad (тест ситуационной осведомлённости); langfuse/opentelemetry, чтобы «я сейчас» собиралось из журнала → mind/self.
- П1 → №6 Память: mem0ai, graphiti-core (временной граф), letta (sleep-time), sqlite-vec, bge-m3 + reranker; тесты LongMemEval, LoCoMo → mind/memory → S03.
- П1 → №7 Сон и консолидация: letta sleep-time; hdbscan (кластеры концептов) → mind/sleep.
- П1 → №8 Цикл жизни и инициатива: apscheduler, arq + redis; proactive-agent (ProactiveBench) → mind/life.
- П1 → №9 Личность: gpt_roleplay_realm, limloop, PIPPA, Synthetic-Persona-Chat; DPO против угодливости (Anti-Sycophancy-DPO, antislop); trl, mergekit — «потом» → mind/persona.
- П1 → №10 Совесть и безопасность: Qwen3Guard-Gen-0.6B, deberta prompt-injection, granite-guardian, llm-guard; тесты AgentDojo, InjecAgent → mind/conscience.
- П1 → №11 Отношения и люди: модель собеседника, «Дима отдельно»; mem0 user-scoped → mind/people.
- П1 → №12 Время: dateparser, pendulum; блок «сейчас / последний разговор» → mind/time.
- П1 → №13 Голос: T-one, GigaAM, faster-whisper, silero-vad, Qwen3-TTS / CosyVoice3 / FireRedTTS-2, Fish S2 («NC теперь разрешена»), pipecat → organs/voice.
- П1 → №14 Зрение: Qwen3-VL-8B GGUF; MiniCPM-V → organs/vision.
- П1 → №15 Рисунок, правка, видео: Z-Image-Turbo, Qwen-Image-2512, Chroma, Wan 2.2, LTX; GGUF через stable-diffusion.cpp / ComfyUI-GGUF; крупные — ждать места на диске → organs/draw.
- П1 → №16 Руки: openhands, browser-use, playwright; MCP: filesystem, fetch, memory, git → organs/hands.
- П1 → №17 Хищник (ЧЕРВИ, охота, поглощение): huggingface_hub, datasets, PyGithub, feedparser; каталог 13 700 + 5 480 → organs/hunt.
- П1 → №18 Обучение (позже, малое): unsloth, trl, peft, mergekit, repeng; правила круга из канона v5 гл. 10 → train/.
- П1 → №19 Оценка живости: deepeval, inspect-ai, promptfoo; EQ-Bench, RP-Bench, MERA → eval/.
- П1 → №20 Мониторинг и автопоэзис: uptime-kuma/healthchecks, systemd-юниты, restic → ops/.
- П1 → Порядок → 1) малое и pip сразу; 2) готовые диалоги и ответы сразу в обучение и в S03 как пример стиля; 3) модели по месту на диске; 4) подключение в живой контур через фича-флаг, с бэкапом и командой отката, затем тест из канона v5 по главе.
- П2 → железо → Quadro RTX 8000 48 ГБ (Turing sm_75: нет bf16/FA2; работают GGUF K/I-кванты и fp16; FP8/NVFP4 не использовать), 128 ГБ RAM, llama.cpp.
- П2 → Лидерборды → RuQualBench: ошибки русского на 1000 токенов, ниже = лучше; GigaChat-3.1-Ultra 0.20, DeepSeek V4 Pro 0.28, Gemma 4 26B-A4B 0.45, Qwen3.6-27B 0.69, T-pro-it-2.1 0.86, gpt-oss-20b 15.54.
- П2 → Лидерборды → EQ-Bench Creative таблицы не загрузились; LoreWeaver (продавец моделей, не независим) EQ creative: Kimi K3 5, GLM-5.3 6, Gemma 4 31B 85 из 140.
- П2 → Кандидаты → Gemma 4 26B-A4B-it: Q6_K 23.2 ГБ, Q8_0 26.9 ГБ, влезает в VRAM; «лучший русский среди малых MoE»; EQ не измерен.
- П2 → Кандидаты → Qwen3.6-35B-A3B (текущее «тело»): SWE-bench V 73.4, GPQA 86.0; русский хуже Gemma 4.
- П2 → Кандидаты → GigaChat3.5-432B-A28B: НЕТ по железу; даже Q2 ~130+ ГБ.
- П2 → Кандидаты → DeepSeek V4 Flash (0731): IQ2_XS 85 ГБ, IQ2_M 104 ГБ; «ТЕСНО», нужен свежий llama.cpp; скорость и качество 2-бита не проверены.
- П2 → Кандидаты → GLM-5.3-Flash: НЕТ/на грани; прежний план в Канаде (762 ГБ RAM) на этом сервере неприменим.
- П2 → Кандидаты → Kimi K3 (~1.4 ТБ), Kimi K2.5, DeepSeek V3.2: НЕТ по размеру.
- П2 → Кандидаты → gpt-oss-120b/20b: ОТКЛОНИТЬ как «мозг» для русского; допустимо только как учитель логики.
- П2 → Кандидаты → uncensored-варианты (Huihui-Qwen3.5 abliterated, Qwen3.6 heretic, SuperGemma4 abliterated): «свободный от отказов» вариант; русский после abliteration не проверен.
- П2 → Кандидаты → RP-тюны Gemma 4 (Kanimus, WaifuGemma4, VisualNovel): только названия, языки и качество не проверены.
- П2 → Кандидаты → «Готовых русских RP/companion-тюнов на базе 2026-поколения не найдено»; Vikhr-тюн под Qwen3.6/Gemma 4 не существует (по поиску).
- П2 → ТОП-3 для тела NOX → 1) Gemma 4 26B-A4B-it Q6_K/Q8_0 в VRAM — основное «тело» живого разговора (RuQual 0.45 против 0.64 у Qwen-35B-A3B); риск: услужливость в роли; проверять слепым A/B на 20 русских диалогах.
- П2 → ТОП-3 → 2) Qwen3.6-35B-A3B оставить как «рассуждатель/инструментальщик» (режим «Глубоко», tool-calls).
- П2 → ТОП-3 → 3) DeepSeek V4 Flash IQ2_S_XL/IQ2_M как «большой судья по вызову» (RAM + offload); запасной: Gemma 4 31B dense Q4_K_M.
- П2 → Сравнение → «не заменять, а добавить Gemma 4 26B-A4B как голос/тело и оставить Qwen3.6 как ум».
- П2 → Не проверено → EQ-Bench 3, Creative Writing v3, MERA; скорость на Turing; русский у GLM-5.3-Flash, Mistral Small 4, Qwen3.8.
- П3 → железо → Quadro RTX 8000 48 GB, нет bf16/FA2 → fp16; vLLM/FA2 могут не работать; латентность почти нигде не измерена на Turing, нужен свой замер.
- П3 → A. TTS → Qwen3-TTS 0.6B/1.7B: Apache-2.0, русский (10 языков), до 97 мс e2e (заявлено), инструкции эмоций и voice design; «единственный Apache + ru + стриминг + управление эмоцией».
- П3 → A. TTS → Fun-CosyVoice3 0.5B: двойной стриминг (текст in + аудио out) «идеален под LLM-токены»; лицензия не указана.
- П3 → A. TTS → FireRedTTS-2: Apache-2.0, ru есть; длинные диалоги, стриминг.
- П3 → A. TTS → Fish Audio S2 Pro: коммерция только по отдельной лицензии → НЕТ; теги [laughing] [sigh] [whisper].
- П3 → A. TTS → Fish S1-mini: CC-BY-NC-SA → НЕТ.
- П3 → A. TTS → Chatterbox Multilingual: MIT (веса NVIDIA — отдельное соглашение); ползунок exaggeration 0–1.
- П3 → A. TTS → Higgs Audio v3: Research/Non-Commercial → НЕТ; лидер по эмоциям на EmergentTTS (заявлено автором).
- П3 → A. TTS → F5-TTS-Russian: CC-BY-NC-SA → НЕТ; ESpeech-TTS-1: Apache-метка, юридически проверить (F5 базовые веса NC).
- П3 → A. TTS → Step-Audio-EditX 3B: «доэмоционировать» готовую реплику (только обзор, ru не подтверждён).
