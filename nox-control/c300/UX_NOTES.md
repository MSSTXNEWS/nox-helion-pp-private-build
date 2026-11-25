# UX_NOTES: замечания по чужим зонам (исправляют C и U)
Снимок: локальный обход Playwright 1440/390, 2026-11-25.
- chat.html (C): на 1440 22 sl-icon-button без aria-label/label (проверить, что у каждой есть label); /cal/events даёт 404 (мини-календарь без обработки?); 62 цели <40 px на 1440 (в основном плотные чипы/иконки колонок) - довести до 44 px хотя бы по hit-area.
- creative.html (U): 45 sl-icon-button без label на 1440; на 390 ссылка #k8-live («Обучение: раунд») высотой 25 px - поднять до 44; нет h1 (заголовок страницы).
- index.html (U): 404 иконки layout-split.svg (нет в tabler outline, заменить на layout-columns или layout-sidebar); /cal/events 404.
- settings.html (U): без замечаний по обходу.
