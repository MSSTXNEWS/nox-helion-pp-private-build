"""CON-10: аудит NOX по индикаторам Butlin, Long и др. (arXiv 2308.08708): таблица «индикатор -> артефакт -> доказательство -> пробел».

Честная рамка: это инвентаризация функциональных механизмов, НЕ вывод «NOX сознателен» (авторы статьи тоже говорят «индикаторы», не доказательство).
14 индикаторов: RPT-1/2, GWT-1..4, HOT-1..4, AST-1, PP-1, AE-1/2. Статус каждого из {нет, частично, функционально}:
  функционально = код-артефакт найден И в трассах/журналах есть накопленные данные (порог min);
  частично      = есть код ИЛИ часть кода, но трассы пусты/мало;   нет = артефакта нет.
Вывод: JSON (по умолчанию $NOX_STATE/indicator_audit.json) + строка в журнал жизни (kind=event, source=audit).
Запуск: python3 indicator_audit.py [--force] [--out PATH] [--state DIR] [--roots A:B]; без --force раз в 7 суток. Код 0 всегда, если файл записан.
"""
import os as _os, sys as _sys  # общие модули COMMON
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import argparse
import json
import os
import sys
import time

import statefile
import lifelink

HERE = os.path.dirname(os.path.abspath(__file__))
STATUSES = ("нет", "частично", "функционально")
WEEK = 7 * 86400
DISCLAIMER = ("Аудит функциональных индикаторов (Butlin и др. 2023). Не является утверждением о наличии сознания или переживания у NOX; "
              "у системы нет теста, который бы это решал.")

# Проверки: ("code", файл, подстрока) | ("jsonl", файл_в_state, мин_записей) | ("json", файл_в_state, путь.через.точку, мин_значение)
IND = [
    {"id": "RPT-1", "theory": "RPT", "name": "Алгоритмическая рекуррентность во входных модулях",
     "artifact": "нет (LLM-вызов: трансформер без рекуррентных входных модулей)", "checks": [],
     "gap": "Входные модули NOX - вызовы языковой модели и сенсоры тела; алгоритмической рекуррентности внутри восприятия нет."},
    {"id": "RPT-2", "theory": "RPT", "name": "Организованные перцептивные представления (гештальт-сцены)",
     "artifact": "нет (сенсоры дают числа/текст, сцены не строятся)", "checks": [],
     "gap": "Нет модуля, строящего целостные сцены из сенсорного потока."},
    {"id": "GWT-1", "theory": "GWT", "name": "Параллельные специализированные подсистемы",
     "artifact": "CON/nox_workspace.py: сенсоры body/drive/fear/memory/thought/owner постят сигналы",
     "checks": [("code", "nox_workspace.py", "KIND_WEIGHT"), ("code", "nox_workspace.py", "def post")],
     "gap": "Подсистемы работают в одном процессе по очереди, а не параллельно."},
    {"id": "GWT-2", "theory": "GWT", "name": "Рабочее пространство ограниченной ёмкости с отбором",
     "artifact": "CON/nox_workspace.py: Workspace.compete (порог зажигания, привыкание)",
     "checks": [("code", "nox_workspace.py", "def compete"), ("jsonl", "thoughts.jsonl", 20)],
     "gap": "Нужны накопленные победители конкурса в thoughts.jsonl (>=20), чтобы видеть ротацию фокуса."},
    {"id": "GWT-3", "theory": "GWT", "name": "Глобальная рассылка победителя всем подсистемам",
     "artifact": "CON/nox_workspace.py: subscribe/broadcast + блок «Я сейчас»",
     "checks": [("code", "nox_workspace.py", "def subscribe"), ("code", "nox_workspace.py", "render_block"), ("jsonl", "thoughts.jsonl", 20)],
     "gap": "Подписчиков мало: рассылка идёт в блок промпта, а не во все модули ядра."},
    {"id": "GWT-4", "theory": "GWT", "name": "Зависимое от состояния внимание (последовательные запросы к модулям)",
     "artifact": "CON/nox_inner_loop.py: шаг цикла опирается на предыдущую мысль (рекуррентность через ws.post)",
     "checks": [("code", "nox_inner_loop.py", "рекуррентность"), ("jsonl", "thoughts.jsonl", 20)],
     "gap": "Цепочки запрос-ответ между модулями короткие (1 шаг)."},
    {"id": "HOT-1", "theory": "HOT", "name": "Генеративные, управляемые top-down модули восприятия",
     "artifact": "нет (восприятия как такового нет; есть только языковая модель)", "checks": [],
     "gap": "Нет генеративной модели входа, подстраиваемой ожиданиями."},
    {"id": "HOT-2", "theory": "HOT", "name": "Метакогнитивный мониторинг: отличать надёжное от шума",
     "artifact": "CON/nox_self_model_live.py: predict/resolve/calibration (Brier) для уверенности мыслей",
     "checks": [("code", "nox_self_model_live.py", "def calibration"), ("json", "self_live.json", "predictions", 10)],
     "gap": "Калибровка покрывает только мысли внутреннего цикла, не ответы чата."},
    {"id": "HOT-3", "theory": "HOT", "name": "Агентность, ведомая убеждениями и метамониторингом",
     "artifact": "BRAIN/conscience.py + ACT/gap_map.py: действия сверяются с самооценкой и квитанциями",
     "checks": [("code", "conscience.py", "def "), ("code", "gap_map.py", "def ")],
     "gap": "Убеждения обновляются по журналу и квитанциям, но не через единый механизм доверия."},
    {"id": "HOT-4", "theory": "HOT", "name": "Разреженное и гладкое кодирование (пространство качеств)",
     "artifact": "частично косвенно: EMO/emotion_pad.py (PAD - непрерывное пространство состояний)",
     "checks": [("code", "emotion_pad.py", "class "), ("jsonl", "emo_calib.jsonl", 7)],
     "gap": "PAD - 3 числа по гипотезе, а не выученное разреженное пространство качеств."},
    {"id": "AST-1", "theory": "AST", "name": "Предсказательная модель собственного внимания",
     "artifact": "CON/nox_workspace.py: Workspace.schema() (что в фокусе, почему, что вытеснено, как долго)",
     "checks": [("code", "nox_workspace.py", "def schema"), ("jsonl", "thoughts.jsonl", 20)],
     "gap": "Модель внимания описательная: будущий фокус она не предсказывает и не проверяется."},
    {"id": "PP-1", "theory": "PP", "name": "Предиктивное кодирование во входных модулях",
     "artifact": "частично: прогнозы уверенности сверяются с исходом (CON predict/resolve)",
     "checks": [("code", "nox_self_model_live.py", "def predict"), ("json", "self_live.json", "predictions", 30)],
     "gap": "Предсказывается собственная уверенность, а не сенсорный вход."},
    {"id": "AE-1", "theory": "AE", "name": "Агентность: обучение по обратной связи, гибкие цели",
     "artifact": "ACT/task_runner.py + квитанции; MEM/correction.py (поправки владельца)",
     "checks": [("code", "task_runner.py", "receipt"), ("code", "correction.py", "def "), ("dir", "receipts", 3)],
     "gap": "Цели задаёт владелец; самостоятельное порождение целей ограничено (инициатива в тихих часах отключена)."},
    {"id": "AE-2", "theory": "AE", "name": "Воплощение: модель связи «выход -> вход» и использование её для управления",
     "artifact": "WORLD/self_atlas.py: живой атлас тела (RAM/CPU/GPU) + CON living self-model",
     "checks": [("code", "self_atlas.py", "def "), ("json", "self_live.json", "boots", 1)],
     "gap": "Тело - сервер: связь «действие -> изменение метрик» не моделируется явно."},
]


def _roots(roots=None):
    r = roots if roots is not None else [x for x in os.environ.get("NOX_CODE_ROOTS", "").split(os.pathsep) if x]
    return r or [os.path.abspath(os.path.join(HERE, ".."))]


def _find(roots, name):
    for root in roots:
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in (".git", "__pycache__", "node_modules", "DEPLOY", "WEB")] if dp == root else [d for d in dns if d not in (".git", "__pycache__", "node_modules")]
            if name in fns:
                return os.path.join(dp, name)
    return None


def _jsonl_n(path):
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for l in f if l.strip())
    except OSError:
        return 0


def _dig(obj, path):
    for k in path.split("."):
        if isinstance(obj, dict) and k in obj:
            obj = obj[k]
        else:
            return None
    return obj


def run_check(chk, state, roots):
    """-> (ok: bool, текст-доказательство, kind: code|trace)."""
    t = chk[0]
    if t == "code":
        p = _find(roots, chk[1])
        if not p:
            return False, "нет файла %s" % chk[1], "code"
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                ok = chk[2] in f.read()
        except OSError:
            ok = False
        return ok, "%s: %s «%s»" % (chk[1], "содержит" if ok else "не содержит", chk[2]), "code"
    if t == "jsonl":
        n = _jsonl_n(os.path.join(state, chk[1]))
        return n >= chk[2], "%s: %d записей (нужно >=%d)" % (chk[1], n, chk[2]), "trace"
    if t == "json":
        try:
            with open(os.path.join(state, chk[1]), encoding="utf-8") as f:
                v = _dig(json.load(f), chk[2])
        except (OSError, ValueError):
            v = None
        n = len(v) if isinstance(v, (list, dict)) else (v if isinstance(v, (int, float)) else 0)
        return n >= chk[3], "%s:%s = %s (нужно >=%d)" % (chk[1], chk[2], n, chk[3]), "trace"
    if t == "dir":
        try:
            n = len([x for x in os.listdir(os.path.join(state, chk[1]))])
        except OSError:
            n = 0
        return n >= chk[2], "%s/: %d файлов (нужно >=%d)" % (chk[1], n, chk[2]), "trace"
    return False, "неизвестная проверка %r" % (t,), "code"


def audit_one(ind, state, roots):
    ev, code_ok, code_all, trace_ok, trace_all = [], 0, 0, 0, 0
    for chk in ind["checks"]:
        ok, text, kind = run_check(chk, state, roots)
        ev.append({"check": text, "ok": ok, "kind": kind})
        if kind == "code":
            code_all += 1
            code_ok += ok
        else:
            trace_all += 1
            trace_ok += ok
    if not ind["checks"] or code_ok == 0:
        st = "нет"
    elif code_ok == code_all and trace_ok == trace_all and trace_all > 0:
        st = "функционально"
    else:
        st = "частично"
    gap = ind["gap"] if st != "функционально" else (ind["gap"] if ind["gap"] else "")
    return {"id": ind["id"], "theory": ind["theory"], "name": ind["name"], "status": st, "artifact": ind["artifact"],
            "evidence": ev, "gap": gap}


def run_audit(state=None, roots=None, now=None):
    state = state or os.environ.get("NOX_STATE", "/root/nox/state")
    roots = _roots(roots)
    rows = [audit_one(i, state, roots) for i in IND]
    cnt = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    return {"source": "arXiv 2308.08708", "ts": now if now is not None else time.time(), "disclaimer": DISCLAIMER,
            "summary": cnt, "indicators": rows}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=os.environ.get("NOX_STATE", "/root/nox/state"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--roots", default=None, help="каталоги кода через ':'")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    out = a.out or os.path.join(a.state, "indicator_audit.json")
    prev = statefile.load(out, None)
    if prev and not a.force and time.time() - prev.get("ts", 0) < WEEK:
        print(json.dumps({"status": "skipped", "reason": "аудит делался менее 7 суток назад", "path": out}, ensure_ascii=False))
        return 0
    rep = run_audit(a.state, a.roots.split(":") if a.roots else None)
    statefile.save(out, rep)
    lifelink.append("event", "Недельный аудит индикаторов Butlin: %s" % ", ".join("%s=%d" % kv for kv in rep["summary"].items()), "audit",
                    state_dir=a.state, data={"summary": rep["summary"]})
    print(json.dumps({"status": "written", "path": out, "summary": rep["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
