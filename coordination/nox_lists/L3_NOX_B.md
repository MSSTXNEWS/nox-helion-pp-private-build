# L3_NOX_B: практические инструменты и дизайн

Исполнитель: NOX-B. Код: `nox-control/practical/`. Инструменты только читают и считают, ничего не деплоят.

| # | Шаг | Критерий приёмки | Статус |
|---|---|---|---|
| B1 | `python3 -m unittest discover -s nox-control/practical` | OK, 0 failures (15 тестов) | TODO |
| B2 | `practical_tools.py list` | 13 инструментов, совпадает с `practical_tools.json` | TODO |
| B3 | `palette_gen` для брендового цвета владельца (спросить цвет), схема triad | для каждого цвета `ratio` >= 4.5 у пары `on`/`hex` или честная пометка AA_text=false | OWNER (цвет) |
| B4 | `css_tokens` из палитры B3, сохранить `tokens.css` для «Резонанса» | `:root` содержит `--color-*`, `--space-*`, `--tap-min: 44px` | TODO |
| B5 | `html_lint` и `a11y_check` на главной «Резонанса» | отчёт со списком; 0 errors в lint, 0 нарушений a11y либо правки в карточку | TODO |
| B6 | `img_optimize_plan` на папке картинок сайта | план: WebP/AVIF, ширины, бюджет 200KB; исполнение отдельно | TODO |
| B7 | `design_brief` для главной «Резонанса» (цель и аудитория от владельца) | бриф с acceptance и открытыми вопросами | OWNER (цель) |
| B8 | `copy_ru` на 3 текстах главной | кавычки «», тире, неразрывные пробелы; список замечаний приложен | TODO |
| B9 | `task_to_pr` для 2 реальных задач + `changelog_gen` по репозиторию | acceptance-карточки с рисками; changelog сгруппирован по префиксам | TODO |
| B10 | `server_status_summary` с портами {"chat":8098,"embed":8082,"searxng":8888} и `deploy_checklist` kind=server | сводка с warnings по закрытым портам; чеклист 7+ пунктов | TODO |

Правила: не менять защищённые файлы V29.3, не деплоить, удалять ничего.
