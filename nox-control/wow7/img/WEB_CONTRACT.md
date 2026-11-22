# IMG: API-контракт для страницы «Графика» (graphics.html)
Сервис: `127.0.0.1:8097` (S1, только localhost; наружу через web_server). В web_server.py: `NOX_IMG=127.0.0.1:8097` (прокси `/v7/graphics/submit` -> `POST /generate` уже есть). Дописать (4 строки) `GET /v7/graphics/status` -> прокси `GET /status` (сейчас там HOLD по пустому NOX_IMG), `GET /v7/graphics/artifact/<id>/<i>.png` -> `/artifact/...`, `POST /v7/graphics/cancel/<id>`, `POST /v7/graphics/unload`.

## POST /generate  (JSON)
Поля страницы: `brief` (идея словами, «общий» ввод), `positive`, `negative`, `general` (общий промпт/стиль серии, добавляется к каждому), `slider` 0..100 (0 быстро ... 100 качество), `aspect` (`1:1|3:2|2:3|16:9|9:16|4:3|3:4`) либо `width`/`height`, `seed`, `n` (1..8, по умолчанию из ползунка), `judge` (bool), `model` (`chroma1-hd|z-image-turbo`, по умолчанию по ползунку), `steps`, `async` (true -> 202 {id}), `real_person_consent` (bool, только если это сам владелец или есть согласие; журналируется), `raw` (true: без мастер-промпта).
Мастер-промпт «ведущий графический дизайнер» подключается автоматически (brief -> positive/negative; без LLM - офлайн-сборка; ответ содержит `notes` и `prompt_source`). Ползунок: <=33 быстро (Z-Image, 9 шагов, 1 картинка), 34-66 баланс (2 картинки + судья), >=67 качество (Chroma 20-40 шагов, >=80: несколько картинок + судья + перегенерация раунда).
Ответ 200: `{id, state:"done", images:[{index, seed, sha256, bytes, url, judge}], best, receipt_url, receipt_sha256, notes, timings:{warm_s, vram_wait_s, to_gpu_s, gen_s, total_s}, model}`; `?inline=1` добавляет `png_base64`.
Коды: 202 принято (async), 400 неверный запрос, 403 отказ жёсткого правила `{error:"refused", rule:"csam|real_intimate|fake_document", reason, field}`, 429 очередь полна, 503 нет весов / нет VRAM / мало RAM (`weights_not_installed|vram_unavailable|ram_low`), 504 таймаут, 409 отменено.
Правила: показывать `reason` как есть; кнопки «обойти» нет. Для `real_intimate` страница может предложить флажок согласия.
## GET /status
`{state: idle|warming|waiting_vram|generating|unloading|judging, running:{id,step,steps,image,n}, queued, models:{<key>:{role,repo,license,installed,where:cold|ram|gpu}}, vram_free_mb, window, counters, mem_available_gb}`. Для честного статуса: нет весов -> `installed:false` (UI: HOLD), не фальшивый процент.
## GET /status/<id>
Состояние задачи + `result` когда `done`. Опрос раз в 1 с; прогресс `step/steps`, `image/n`.
## Прочее
`GET /artifact/<id>/<i>.png`, `GET /receipt/<id>` (квитанция с SHA и цепочкой `prev`), `POST /cancel/<id>`, `POST /unload {scope:"ram|gpu|all", model?}` (409 если идёт генерация), `GET /refusals`, `POST /pause|/resume`.
Совместимость: `POST /v1/images/generate[?format=json]`, `GET /v1/images/jobs/<id>`, `POST /v1/images/jobs/<id>/cancel` - для imagegen/tool.py без изменений.
## Быстрые команды страницы (теги) -> готовые `general`/`slider`
«кинокадр» (general: cinematic still, anamorphic, film grain), «аниме-постер», «концепт-арт», «фотореализм», «логотип/иконка», «пиксель-арт», «взрослая арт-съёмка» (ничего не режется, кроме трёх жёстких правил). Теги только подставляют текст в поля.
