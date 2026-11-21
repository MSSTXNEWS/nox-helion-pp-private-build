# Промпты для генерации изображений: правила и 8 примеров для навыков NOX

Инструмент: `generate_image` (сервис 127.0.0.1:8096). Основная модель - FLUX.1-schnell, запасная - SDXL-чекпойнт.

## Правила хорошего промпта

1. Пиши по-английски: обе модели обучены на англоязычных подписях.
2. Порядок: субъект, действие/поза, окружение, стиль/носитель, свет, ракурс/объектив, палитра. Главное - в начало.
3. Одно предложение на сцену, конкретные существительные вместо «красивый, эпичный, 8k, masterpiece». Теги-заклинания FLUX не нужны.
4. Количество и цвет называй прямо: «three red apples», «a woman in a yellow raincoat».
5. Текст на картинке - в кавычках и коротко (до 3-4 слов): `a neon sign that reads "OPEN"`. Длинный текст модель исказит.
6. FLUX.1-schnell: 4 шага, без negative и без CFG (поле negative игнорируется). Неудачу чини переписыванием промпта, не шагами.
7. SDXL: 25-35 шагов, guidance 5-7, negative работает: `blurry, extra fingers, watermark, text`.
8. Размер: 1024x1024 по умолчанию; портрет 832x1216, пейзаж 1216x832. Кратно 16, не больше 1536x1536. На S1 большие размеры идут минуты (CPU-offload).
9. Воспроизводимость: фиксируй seed и меняй одну вещь за раз.
10. Проверка: `check: true` отправляет результат судье зрения (если настроен NOX_VISION_URL); при ok=false перепиши промпт по `reasons`.
11. Жёсткие запреты сервиса: сексуальный контекст с несовершеннолетними (включая стилизованных детей) и откровенные изображения реальных людей без согласия. Сервис ответит отказом с причиной (403) - не пытайся обходить формулировками.

## 8 примеров

1. Фотореализм, портрет.
   `Close-up portrait of an elderly fisherman with a weathered face and white beard, soft overcast light, 85mm lens, shallow depth of field, muted blue-grey tones` (832x1216)
2. Продуктовое фото.
   `A matte black ceramic coffee mug on a walnut table, steam rising, morning window light from the left, minimalist composition, studio product photography` (1024x1024)
3. Интерфейс/иконка.
   `Flat vector app icon of a hummingbird made of geometric shapes, teal and orange on a dark navy rounded square, clean edges, no text` (1024x1024)
4. Концепт-арт, пейзаж.
   `Wide concept art of a floating monastery among cloud layers at sunrise, long stone bridges, tiny pilgrims, warm gold light against cold violet shadows, painterly` (1216x832)
5. Аниме/иллюстрация.
   `Anime style illustration of a girl in a yellow raincoat holding a transparent umbrella on an empty night street, neon reflections on wet asphalt, cinematic framing` (832x1216)
6. Текст на картинке.
   `Retro travel poster of Lisbon trams on a hill, bold flat colors, large title text that reads "LISBOA"` (832x1216)
7. Схема/инфографика (простая).
   `Clean isometric diagram of a small server rack connected to a cloud, white background, thin blue lines, soft shadows, no text` (1216x832)
8. Серия с единым стилем (фиксируй seed, меняй субъект).
   `Watercolor illustration of a red fox sleeping in autumn leaves, soft paper texture, limited palette of ochre, rust and sage` -> затем та же фраза с `a heron standing in a pond` и `an owl on a bare branch`, тот же seed и стиль.

## Цикл «сгенерировать - проверить - поправить»

1. `generate_image(prompt, check=true)`.
2. `judge.ok == true` - отдать путь к файлу. `ok == false` - один раз переписать промпт, учитывая `reasons`, и повторить; не больше 2 повторов.
3. `judge.configured == false` - судья зрения не настроен: честно сказать об этом и показать результат без оценки.
4. `error == "weights_not_installed"` или `service_unreachable` - сказать владельцу прямо, что сервис/веса недоступны; не подменять картинку заглушкой.
