# DESIGN100: функции страницы дизайнера (creative.html)

Топ-3 референса для раскладки: Figma (панели, свойства, слои), Photoshop web/Firefly (маски, gen fill, история), Krea + tldraw make-real (рисуй -> ИИ перерисует). Изучены также Canva Magic Studio, Recraft, Leonardo Canvas, Kittl, Penpot, Photopea (зум, пиксели).
Статус: [x] сделано в nox-dz-creative.js, [ ] отложено.

| # | Функция | У кого | Модуль | Как в ИИ |
|---|---|---|---|---|
| 1 | Выбор/перемещение (V) | Figma, Photoshop | Fabric select | ИИ видит выделенные объекты как JSON |
| 2 | Прямая выделения / правка узлов | Figma, Penpot | Fabric controls | JSON пути |
| 3 | Рамка/артборд (F) | Figma | Fabric Rect + clip | размер холста в контексте |
| 4 | Прямоугольник (R) | Figma, Canva | Fabric Rect | объект в JSON |
| 5 | Эллипс (O) | Figma | Fabric Ellipse | объект в JSON |
| 6 | Линия (L) | Figma | Fabric Line | объект в JSON |
| 7 | Стрелка | Excalidraw, tldraw | Fabric Line+Triangle | объект в JSON |
| 8 | Многоугольник/звезда | Figma, Kittl | Fabric Polygon | объект в JSON |
| 9 | Перо Безье (P) | Figma, Photoshop, Penpot | Fabric Path (клики) | SVG path в ИИ |
| 10 | Кисть (B) | Photoshop, Krea | Fabric PencilBrush | PNG холста |
| 11 | Карандаш/каракули | tldraw, Krea | PencilBrush тонкая | PNG: каракули -> ИИ |
| 12 | Маркер/прозрачная кисть | Photoshop | PencilBrush alpha | PNG |
| 13 | Размер/жёсткость/прозрачность кисти | Photoshop | sl-range | параметры в промпт стиля |
| 14 | Ластик (E) | Photoshop, Canva | Fabric EraserBrush/удаление | PNG |
| 15 | Заливка (G) | Photoshop | Fabric fill | JSON |
| 16 | Градиент линейный/радиальный | Figma, Photoshop | fabric.Gradient | JSON |
| 17 | Пипетка (I) | Photoshop, Figma | canvas getImageData | цвет в палитру |
| 18 | Текст (T) | Figma, Canva, Kittl | fabric.Textbox | JSON, текст остаётся текстом |
| 19 | Шрифт/размер/начертание/выравнивание | Figma, Canva | sl-select/sl-input | JSON |
| 20 | Межстрочный/межбуквенный | Figma | Textbox lineHeight/charSpacing | JSON |
| 21 | Текст по пути/дуга | Kittl, Illustrator | Textbox + Path | нет, локально |
| 22 | Вставка изображения | все | FileReader + fabric.FabricImage | PNG |
| 23 | Drag&drop/вставка из буфера | Figma, Canva | paste/drop | - |
| 24 | Обрезка (crop) | Photoshop, Canva | clipPath | PNG |
| 25 | Рука/панорама (H, пробел) | Figma | viewportTransform | - |
| 26 | Зум 10%-3200% (Ctrl+колесо) | Figma, Photopea | setZoom | - |
| 27 | Пиксельная сетка при зуме | Figma, Photopea | overlay canvas | - |
| 28 | Режим без сглаживания (pixel) | Photopea | imageSmoothing=false | - |
| 29 | Линейки | Figma, Photoshop | DOM-линейки | - |
| 30 | Направляющие | Figma | объекты линий | - |
| 31 | Сетка и привязка к сетке | Figma, Canva | snap grid | - |
| 32 | Умные направляющие/привязка к объектам | Figma, Canva | object:moving snap | - |
| 33 | Точные X/Y/W/H/угол | Figma | sl-input number | JSON |
| 34 | Выравнивание (6 кнопок) | Figma, Canva | ручной расчёт | - |
| 35 | Распределить по горизонтали/вертикали | Figma | расчёт | - |
| 36 | Группировать/разгруппировать (Ctrl+G) | Figma | fabric.Group | группы = смысловые слои |
| 37 | Порядок: наверх/вниз | Figma, Photoshop | bringToFront | - |
| 38 | Дублировать (Ctrl+D) | Figma | clone | - |
| 39 | Копировать/вставить | все | clipboard obj | - |
| 40 | Отразить Г/В | Figma | flipX/flipY | - |
| 41 | Поворот на 90 | Figma | angle | - |
| 42 | Блокировка слоя | Figma | lockMovement | - |
| 43 | Видимость слоя (глаз) | Figma, Photoshop | visible | - |
| 44 | Переименование слоя | Figma | obj.name | имена слоёв идут в ИИ |
| 45 | Список слоёв drag-сортировка | Figma | sortablejs | порядок в JSON |
| 46 | Прозрачность объекта | Figma, Photoshop | opacity | JSON |
| 47 | Режимы наложения | Photoshop | globalCompositeOperation | JSON |
| 48 | Заливка и обводка цвет | Figma | sl-color-picker | JSON |
| 49 | Толщина/стиль обводки (пунктир) | Figma | strokeDashArray | JSON |
| 50 | Скругление углов | Figma | rx/ry | JSON |
| 51 | Тень | Figma, Canva | fabric.Shadow | JSON |
| 52 | Размытие объекта | Figma, Photoshop | filters.Blur | JSON |
| 53 | Маска слоя (clipPath) | Photoshop | clipPath | маска как PNG |
| 54 | Маска кистью (выделение) | Photoshop, Krea | отдельный слой маски | PNG маски + оригинал |
| 55 | Лассо | Photoshop | Polygon из точек | PNG маски |
| 56 | Магнитное/прямоугольное выделение | Photoshop | Rect mask | PNG маски |
| 57 | Инвертировать маску | Photoshop | pixel op | PNG маски |
| 58 | Растушёвка маски | Photoshop | blur mask | PNG маски |
| 59 | Фильтры: яркость/контраст/насыщ. | Canva, Photopea | fabric.filters | - |
| 60 | Фильтры: ч/б, сепия, инверсия | Canva | fabric.filters | - |
| 61 | Кривые/уровни (упрощённо) | Photoshop | filters Gamma | - |
| 62 | Палитра цветов, недавние | Figma | sl-color-picker swatches | - |
| 63 | Палитра из изображения | Canva, Adobe Color | fast-average-color+квантование | ИИ+локально |
| 64 | Цвет: контраст WCAG | Figma plugins | colorjs.io | - |
| 65 | История: отмена/повтор | все | стек JSON | - |
| 66 | Панель истории (шаги, клик) | Photoshop | стек snapshots | - |
| 67 | Автосохранение | Figma | localStorage | - |
| 68 | Сохранить/открыть проект JSON | Figma | JSON файл | - |
| 69 | Экспорт PNG | все | toDataURL | - |
| 70 | Экспорт JPG/WebP с качеством | Canva | toDataURL | - |
| 71 | Экспорт SVG | Figma | toSVG | - |
| 72 | Экспорт 1x/2x/4x | Figma | multiplier | - |
| 73 | Экспорт выделения | Figma | toDataURL crop | - |
| 74 | Копировать как PNG в буфер | Figma | ClipboardItem | - |
| 75 | Размер холста/пресеты (соцсети) | Canva | setDimensions | - |
| 76 | Фон холста/прозрачный | Canva | backgroundColor | - |
| 77 | Горячие клавиши + подсказки | Figma | tooltip sl-tooltip | - |
| 78 | Окно горячих клавиш (?) | Figma | диалог | - |
| 79 | Контекстная панель свойств (сверху) | Figma, Canva | рендер по типу | - |
| 80 | Контекстное меню ПКМ | Figma | меню | - |
| 81 | Мобильный режим: нижняя панель | Canva | CSS | - |
| 82 | ИИ: каракули -> перерисовать (SVG-слои) | Krea, tldraw make real | vision :8104 | PNG холста + инструкция -> SVG с группами |
| 83 | ИИ: скетч -> вектор | Recraft, Illustrator | vision | PNG -> SVG |
| 84 | ИИ: скетч -> изображение | Krea, Leonardo | /img/generate (выкл.) | PNG; честное «недоступно» |
| 85 | ИИ: сделай HTML/UI из наброска | tldraw make real, Figma Make | vision | PNG -> HTML в iframe-слой |
| 86 | ИИ: улучшить выделенное | Firefly, Canva | vision | PNG выделения |
| 87 | ИИ: перерисовать в стиле | Recraft, Krea | vision + пресеты стилей | PNG+стиль |
| 88 | ИИ: описать выделение | Figma, Photoshop | vision | PNG выделения -> текст |
| 89 | ИИ: альт-текст | Figma | vision | PNG |
| 90 | ИИ: палитра из изображения | Canva, Adobe | vision + локально | PNG -> JSON цветов |
| 91 | ИИ: подбор шрифта | Canva, Adobe | vision | PNG текста -> список шрифтов |
| 92 | ИИ: авто-layout/выровнять | Figma | vision + JSON | JSON объектов -> новые координаты |
| 93 | ИИ: критика дизайна | Figma | vision | PNG -> текст/правки |
| 94 | ИИ: сгенерировать 4 варианта | Krea, Leonardo | vision x4 | SVG-варианты |
| 95 | ИИ: сгенерировать логотип | Recraft, Kittl | vision | SVG |
| 96 | ИИ: переписать текст | Canva | vision/текст | JSON текстов |
| 97 | ИИ: перевести текст на слоях | Figma | текст | JSON текстов |
| 98 | ИИ: удалить фон | Photoshop, Canva | /img (выкл.) + локальный вариант: маска кистью | PNG |
| 99 | ИИ: расширить холст (outpaint) | Firefly, Leonardo | /img (выкл.) | PNG |
| 100 | ИИ: заливка по выделению (gen fill) | Photoshop | /img (выкл.) | PNG+маска |
| 101 | ИИ: апскейл | Krea, Photoshop | /img (выкл.) | PNG |
| 102 | План перед выполнением (что меняю/не трогаю) | ТЗ владельца | нижний диалог | план из модели + подтверждение |
| 103 | Режимы: выделенное/остальное/стиль/фон | ТЗ владельца | маска + композитинг | невыделенное берём из оригинала |
| 104 | Пресеты Фото-реализм/Портрет/Природа/Оригинал | ТЗ владельца | PHOTOREAL100.md | в промпт |
| 105 | Прогресс, отмена, таймаут 2 мин | ТЗ | AbortController | - |
