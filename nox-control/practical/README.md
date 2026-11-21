# NOX practical tools

Практические инструменты под задачи владельца (NOX, сервер, веб «Резонанс», дизайн). Только stdlib Python 3.
Манифест: `practical_tools.json`. Реализация: `practical_tools.py`. Все инструменты только читают и считают:
ничего не деплоят, не удаляют и не отправляют (кроме `advisor_review` — запрос советникам из указанного конфига).

Ответ: `{"ok":true,...}` или честное `{"ok":false,"blocked":"...","need":"..."}`.

```
python3 nox-control/practical/practical_tools.py palette_gen --json '{"base":"#1a73e8","scheme":"triad"}'
python3 nox-control/practical/practical_tools.py a11y_check --file page.json   # {"html":"..."}
python3 nox-control/practical/practical_tools.py list
python3 -m unittest discover -s nox-control/practical
```

| Инструмент | Что делает |
|---|---|
| design_brief | бриф: цель, аудитория, принципы, acceptance, открытые вопросы |
| palette_gen | палитра (mono/analogous/complementary/triad/split) + контраст WCAG по формуле относит. яркости |
| css_tokens | `:root` переменные: цвета, отступы, шкала шрифтов, `--tap-min: 44px` |
| a11y_check | lang, alt, подписи полей, пустые ссылки/кнопки, цели < 44px, контраст inline-стилей, порядок заголовков |
| html_lint | doctype, title, viewport, charset, незакрытые/лишние теги, дубли id, устаревшие теги |
| img_optimize_plan | размеры из заголовков PNG/JPEG/GIF/WebP, бюджет KB, WebP/AVIF, srcset (только план) |
| screenshot_diff_plan | матрица страниц x viewport, пути baseline/current, порог (только план) |
| copy_ru | кавычки «», тире, неразрывные пробелы после предлогов, длинные предложения, капс |
| task_to_pr | текст задачи -> ветка, шаги с проверкой, acceptance, риски (прод/удаление/ключи/V29.3) |
| changelog_gen | Markdown из `git log`, группировка по префиксу (`c52:`, `fix:`) |
| deploy_checklist | чеклист web / nox / server (не деплоит) |
| server_status_summary | load, память, swap, диск, uptime, проверка портов 127.0.0.1 из `ports` |
| advisor_review | `nox_advisors.review` по конфигу советников, с меткой «мнение советника, не NOX» |

Ограничения: a11y_check видит только inline-стили (без CSS-файлов и рендера); image/screenshot — планы, исполнение за владельцем.
