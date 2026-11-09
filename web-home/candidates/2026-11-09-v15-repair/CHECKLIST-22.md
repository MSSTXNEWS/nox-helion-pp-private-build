# NOX HELION — проверка утверждённых 22 блоков (09.11.2026)

Кандидат: [V15 preview](https://nox-helion-real-home-preview-d7hrdljj6-msttx.vercel.app/), deployment `dpl_ChLDzseHXhGkUoFenSyEs516Yzb7`. **Ниже перечислены не завершённые задачи, а проверяемые критерии и текущие свидетельства.**

| № | Критерий ТЗ | Факт 09.11.2026 | Статус |
|---|---|---|---|
| 01 | Оригинальный WebGL D02 | `nox-home.mjs` отдаёт 200, мастер есть | GPU HOLD |
| 02 | Резерв при потере WebGL | `nox-home-recovery.js`, heartbeat/context guard в публикации | Source verified / browser HOLD |
| 03 | Чёрное монолитное небо | Восстановлены CSS и несколько приглушённых фоновых сценариев | Source verified / visual HOLD |
| 04 | 14 объектов: 6+5+3 | `nox-orbit-original.js`, PBR renderer присутствуют | Source verified / visual HOLD |
| 05 | Реалистичные PBR-материалы планет | `MeshPhysicalMaterial`, texture loader | Texture/GPU HOLD |
| 06 | Три разных астероида + NASA Bennu | Код геометрии и STL loader | Remote asset/runtime HOLD |
| 07 | Нет расстановки «как часы» | Ассиметричное позиционирование и independent frequencies в коде | Runtime HOLD |
| 08 | Приближение, отталкивание и контакты | Collision guard, impulse и sliding в JS | Natural collisions HOLD |
| 09 | Вращение планет вокруг осей | Угловые скорости в PBR и CSS | Motion observation HOLD |
| 10 | Кинематографическая смена света | Дирижёр и light-change event присутствуют | Screenshot HOLD |
| 11 | 6 цветовых карт | Кнопки и состояние описаны в коде | Interaction HOLD |
| 12 | 5 обликов/тем | Кнопки и CSS темы описаны в коде | Interaction HOLD |
| 13 | 3 графических режима | MAX/BALANCED/ECO в коде | GPU budget HOLD |
| 14 | Reduced Motion | Отдельные правила, fallback state refresh исправлен | Browser HOLD |
| 15 | Резонанс — ведущая кнопка | Динамическая координата заголовка, `chat.html` HTTP200 | Visual/accessibility HOLD |
| 16 | Верхняя навигация | Присутствует в исходниках | Interaction HOLD |
| 17 | Нижние кнопки без потери маршрутов | HOME + 9 разделов отдают HTTP200 | Route HTTP PASS / click HOLD |
| 18 | Адаптивность 320–4K | Есть media queries | Multi-viewport screenshot HOLD |
| 19 | Метрики CPU/GPU/VRAM без выдуманных значений | Public preview показывает неизвестные значения | Honest preview / live HOLD |
| 20 | Chat, Memory S03, Training, Models, Projects | Страницы доступны HTTP200, локальный API не подключён | Integration HOLD |
| 21 | Голос RU/ES, обучение GPU, STOP, SAFE70, установщик | Публичная HOME не доказывает выполнение локальных функций | Native acceptance HOLD |
| 22 | Настоящий GPU, Playwright, скриншоты, регрессия | Проверка через внешний браузер блокировалась Vercel SSO | HOLD |

**Статический итог:** 32/32 целевых URL HTTP 200 (10 страниц + 22 ресурса). Это проверка комплекта, а не функциональная/графическая приёмка.

**Правило:** Только подтверждённые тесты отмечать PASS; производство не трогать, пока нет видео/скриншотов и GUI-тестов на владельческом GPU.