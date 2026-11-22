# SETUP — внешние советники NOX за 5 минут (бюджет 0, Q21)

Сейчас без единого ключа работает только Pollinations (публичные вопросы, 1 запрос в 30 с, GPT-OSS 20B). Чтобы был «совет» из 2–3 разных моделей — получите ключи ниже. Карта и оплата НЕ нужны ни в одном шаге; если сайт требует карту — остановитесь, этот провайдер нам не подходит.

## Шаг 1. Ключи (рекомендую первые три, ~3 минуты)
| # | Провайдер | Страница | Что даёт бесплатно (по докам 22.11.2026) |
|---|---|---|---|
| 1 | Groq | https://console.groq.com/keys | gpt-oss-120b, qwen3.8-27b; 30 запросов/мин, 1000/сутки на модель |
| 2 | Cerebras | https://cloud.cerebras.ai/ (API Keys) | qwen-3.8-27b (300 запр/мин), gpt-oss-120b (5/мин, 1M ток/сутки) |
| 3 | OpenRouter | https://openrouter.ai/settings/keys | модели :free, 20/мин, 50/сутки на все. Кредиты НЕ покупать |
| 4 | Google AI Studio | https://aistudio.google.com/apikey | Gemini flash; лимиты в aistudio.google.com/rate-limit; free-данные могут идти в обучение, поэтому только публичные вопросы |
| 5 | Mistral | https://console.mistral.ai/api-keys | тариф Experiment, лимиты в console.mistral.ai/limits; только публичные вопросы |
| 6 | NVIDIA build | https://build.nvidia.com/ (Get API Key) | trial-эндпоинты (по вторичным данным); только публичные |
| 7 | Cloudflare Workers AI | https://dash.cloudflare.com/profile/api-tokens + Account ID с главной страницы | ~10 000 neurons/сутки; нужны ДВЕ переменные |

Не использовать: GitHub Models (закрыт 30.07.2026), HF Inference (у бесплатных аккаунтов нет кредитов), duck.ai (запрещена автоматизация), платные Claude/Gemini/GPT (Q21).

## Шаг 2. Куда вставить (S1)
Файл `/root/nox/secrets/advisors.env` (создаёт deploy_adv_s1.sh; права 600). Вписать `ИМЯ=ключ` без кавычек:
```
GROQ_API_KEY=...        CEREBRAS_API_KEY=...      OPENROUTER_API_KEY=...
GEMINI_API_KEY=...      MISTRAL_API_KEY=...       NVIDIA_API_KEY=...
CLOUDFLARE_API_TOKEN=...   CF_ACCOUNT_ID=...
NOX_ADV_FREE_CONFIRMED=groq,cerebras,google,mistral,nvidia,cloudflare
```
Последняя строка — ваше подтверждение «к ключу не привязана оплата» (у этих провайдеров нет серверного потолка цены; у OpenRouter он есть и зашит в запрос). Перечислите только тех, чьи ключи получили. Ключи не писать в чат и в git.

## Шаг 3. Запуск
```
bash deploy_adv_s1.sh --dry-run     # посмотреть
bash deploy_adv_s1.sh               # поставить, прогнать тесты, живой опрос, квитанция /root/nox/receipts/ADV-01.json
python3 /root/nox/src/adv/health_check.py --stamp   # после добавления ключей: какие провайдеры реально отвечают
```
Если нет systemd: `nohup /root/nox/scripts/run_advisors.sh &`. Шлюз: проксировать `/v1/advisors/*` на `127.0.0.1:8095` (токен — `NOX_ADV_TOKEN`, по желанию).

## Проверка в чате
«спроси советников: чем отличается mmap от read для больших файлов?» → NOX отвечает сам, называя «советник X сказал…». Варианты: «спроси советников троих …», «… публично с поиском: что нового в …», «спроси gemini вручную: …» (бесплатный веб-чат, вставляете ответ командой «ответ советника man-xxxxxxxxxx: …»).
