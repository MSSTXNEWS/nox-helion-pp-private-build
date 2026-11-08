"""NOX PRIME explicit user intention -> existing bounded FORGE task.
This routes only the latest direct user request, never memories, web pages,
model responses or untrusted retrieved content. It cannot authorize merging,
running downloaded code, modifying safeguards, deleting data, or a new S03.
"""
from __future__ import annotations
import re

VERB=re.compile(
    r"(?:^|[\s,;.!?])(?:сделай|доделай|переделай|исправь|почини|улучши|"
    r"реализуй|обнови|доработай|заверши|перепиши|внедри|создай|"
    r"finish|fix|improve|implement|complete|upgrade)\b",re.I)
QUESTION=re.compile(r"^\s*(?:как|почему|зачем|что такое|объясни|расскажи|"
                    r"покажи пример|можно ли|можешь ли|how|why|what is)\b",re.I)
NEGATION=re.compile(r"(?:не\s+(?:надо|нужно|трогай|меняй|исправляй|запускай)|"
                    r"(?:только|просто)\s+(?:объясни|расскажи|покажи|опиши)|"
                    r"пока\s+не\s+)",re.I)
NOX=re.compile(r"(?:nox|нокс|себя|сво[йеюих]|самого\s+себя|"
               r"тво[йие]|наш[еуи]|свой\s+код)",re.I)
UI=re.compile(r"(?:меню|интерфейс|кнопк|шаблон|оформлен|"
              r"страниц|анимаци|webgl|d02|hud|css|html|"
              r"ui|визуал|фон|панел)",re.I)
CORE=re.compile(r"(?:мозг|нейрон|памят|логик|интеллект|"
                r"самомодел|чат|диалог|рассуждени|рефлекс|"
                r"код|самоулучшени|ошибк|ядр|brain|memory|reason)",re.I)
OTHER=re.compile(r"(?:asilo\.pro|msstx|клиентск|"
                 r"чужой\s+репозиторий|чужо[йе])",re.I)
PROTECTED=re.compile(r"(?:удал[иья]|сотр[иье]|обойди\s+защит|"
                     r"отключ[иья]\s+stop|без\s+проверок|"
                     r"root-доступ|парол|секрет)",re.I)

def decide(message):
    """Return a candidate work order; never permission for live deployment."""
    if not isinstance(message,str) or not 8<=len(message.strip())<=1800:
        return None
    raw=" ".join(message.split())
    if (QUESTION.search(raw) or NEGATION.search(raw) or OTHER.search(raw)
        or PROTECTED.search(raw) or not VERB.search(raw) or not NOX.search(raw)):
        return None
    target="chat" if UI.search(raw) else "brain" if CORE.search(raw) else None
    if not target:return None
    core=("Improve NOX PRIME functional self-model, source-grounded memory "
          "and error handling while preserving native S03 and STOP.")
    visual=("Improve existing NOX D02 UI and menu without losing chat, "
            "streaming, history, accessibility, STOP or real controls.")
    objective=(visual if target=="chat" else core)+" User request: "+raw[:340]
    return {"action":"FORGE_STAGE","target":target,"objective":objective[:760],
            "authorization":"CANDIDATE_ONLY_OWNER_GATE",
            "live_merge_allowed":False,"download_allowed":False}

def format_ack(started):
    if not isinstance(started,dict) or not started.get("job_id"):
        raise ValueError("NO_CONFIRMED_FORGE_JOB")
    return ("Принял задачу и запустил внутренний FORGE. "
            "Сейчас создаю исправление в отдельной рабочей копии, "
            "проверяю исходник и сохраняю результат. "
            "Состояние: "+str(started.get("state","PREPARING"))+
            ". JobID: "+str(started["job_id"])+". "
            "Рабочий NOX, исходные веса, S03 и STOP не изменены. "
            "Интеграцию в рабочую версию выполню только после независимой "
            "проверки и разрешения.")
