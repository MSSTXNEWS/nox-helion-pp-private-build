"""drives: реэкспорт. ЕДИНСТВЕННЫЙ владелец влечений/страхов - EMO/drives.py (REVIEW_1 п.2, исправление 5).

Этот файл оставлен только для старых путей импорта (`import drives` из корня): он подменяет себя модулем EMO/drives.py,
так что класс Drives один и тот же. Новый код импортирует EMO.drives / (в деплое) drives из каталога EMO.
"""
import importlib.util
import os
import sys

_P = os.environ.get("NOX_EMO_DRIVES") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "EMO", "drives.py")
if not os.path.exists(_P):  # деплой: EMO лежит рядом как emo/drives.py
    _P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emo", "drives.py")
_spec = importlib.util.spec_from_file_location("_emo_drives_" + __name__.replace(".", "_"), _P)
_mod = importlib.util.module_from_spec(_spec)
if __name__ == "drives":
    sys.modules["drives"] = _mod     # import drives -> тот же модуль, что EMO/drives.py
_spec.loader.exec_module(_mod)
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})   # и для загрузки по пути (spec_from_file_location)
