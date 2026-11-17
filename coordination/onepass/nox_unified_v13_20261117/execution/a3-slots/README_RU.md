# A3 / 6A04 — дискретные слоты моделей

run_id NOX-49-20261117; исходный TaskID6A04, роль6 и native-критерий сохранены. Native принято0.

Фактический дефект: Budget._remaining применял общий85% коэффициент к model_slots. При capacity1, used/reserved0 и demand1 получалось0.85, поэтому единственный разрешённый слот никогда не использовался. Теперь model_slots — целые счётчики допущенной конкурентности: capacity−used−pending_reserved−chat_reserved. Дробные counts/demand отклоняются до изменения бюджета. Целочисленные float-значения совместимы; bool/NaN/Infinity и отрицательные значения не принимаются.

CPU/RAM/I/O/VRAM/compute остаются раздельными размерностями с85% лимитом. Один слот не отменяет физические бюджеты или chat soft-yield. Второй job при уже занятом единственном слоте отклоняется. Новых callbacks, worker/model/queue нет.

Итоговый блок16/16:6 новых регрессий+10 существующих policy-тестов. Проверены single-slot, резерв pending/chat, дробные counts/demand, неизменность бюджета при отказе, раздельные VRAM/compute ограничения, приоритет чата и zero capacity. Изменены существующий owner_resource_policy.py и только его hash entries в runtime/CURRENT manifests. Код не развёрнут на OneHost.

Запуск: PYTHONPATH=integration/owner_mini_source python -m unittest discover -s execution/a3-slots -p test_discrete_model_slots.py. Остальные10 regression tests — existing quality/role6/tests/test_owner_resource_policy.py. После этого требуются измеренный native snapshot/claims/S03 receipts на принятом SHA; source-тесты не закрывают native карточку.
