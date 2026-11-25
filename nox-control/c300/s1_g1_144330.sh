S=/workspace/nox/web/site
cd $S
cd /workspace/nox/web/site
cat >> qa/rework/chat.fixed <<'F'
S1 (25.11): поле ввода показывается как sl-textarea (авто-рост, Enter отправляет, исходное поле скрыто и получает события), кнопки шапки как sl-button (иконки), «Новый чат» и поиск на sl-*. Проверена реальная отправка: сообщение ушло, ход пошёл «NOX думает».
F
for f in pdf assistant finance; do cat >> qa/rework/$f.fixed <<'F'
S1 (25.11): вкладки на sl-tab-group (событие sl-tab-show переключает панели).
F
done
for f in atlas finance; do cat >> qa/rework/$f.fixed <<'F'
S1 (25.11): ИИ-панель получила таймаут 100 с с понятным сообщением «NOX занят». Проверка реального ответа: на atlas NOX ответил (текстом о сбое черновика), на finance за 120 с ответа не было (модель занята).
F
done
echo ok
