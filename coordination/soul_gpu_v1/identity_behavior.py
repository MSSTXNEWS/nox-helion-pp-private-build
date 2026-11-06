"""NOX HELION / SOUL IDENTITY + BEHAVIOR V1 (SOURCE_ONLY).

A single, persistent persona-state layer for existing soul_gpu.SoulStore SQLite,
NOT a second AI, database or EXE. Canonical references: Drive SOUL LIVING
PERSONAS V2 and FULL OWNER FUNCTION / WISHLIST (2026-10-22).
The inaccessible MAIN V3 was NOT used as an authority. NOX's emotion is a
human-readable behavioral model, NOT scientific evidence of consciousness.
"""

from __future__ import annotations
import json
import re
import time

PERSONA_NAMES = {
    "KV": "Кайрен Восс",
    "AM": "Адриан Мерроу",
    "LA": "Леон Ардис",
    "EV": "Элина Вейл",
    "KW": "Кассиен Вейр",
}
CORE_IDS = ("CONSCIOUSNESS","PERSONA","ATLAS","VOICE","REFLECTION","CORE","NEXUS","FORGE")
FACADES = {
    "HF01":"сознание/планирование", "HF02":"эмоции",
    "HF03":"личность", "HF04":"память", "HF05":"знания",
    "HF06":"развитие", "HF07":"профессии", "HF08":"общение"
}
# Each is an explicit user-approved observable event. The values drive
# behavior, not model-parameter training or verified human feelings.
EVENTS = {
    "success":        (0.16,  0.03, 0.08,  0.08),
    "failure":        (-0.08, 0.06, 0.10, -0.08),
    "discovery":      (0.06,  0.13, 0.18,  0.02),
    "correction":     (-0.02, 0.06, 0.12, -0.05),
    "uncertainty":    (-0.03, 0.07, 0.10, -0.06),
    "collaboration":  (0.09,  0.04, 0.05,  0.05),
    "neutral":        (0.00, -0.02,-0.02,  0.00),
}
BASE = {"valence":0.50,"arousal":0.35,"curiosity":0.62,"confidence":0.50}
PERSONA_HINTS = {
    "KV": "спокойный стратегический подход, внимательное взвешивание последствий",
    "AM": "внимание к системности и последствиям решений",
    "LA": "аналитическая ясность и точность",
    "EV": "внимательность к нюансам общения и контексту",
    "KW": "прагматичная проверка гипотез",
}
# Persona-specific descriptions are temporary behavior defaults, NOT official
# 64+ approved trait passports. Canonical trait import requires owner QA.

def clamp(v):
    return round(max(0.0, min(1.0, float(v))), 4)

def initialize(connection):
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS nox_behavior_state(
          persona TEXT NOT NULL,
          project TEXT NOT NULL,
          valence REAL NOT NULL,
          arousal REAL NOT NULL,
          curiosity REAL NOT NULL,
          confidence REAL NOT NULL,
          last_event TEXT NOT NULL,
          updated_at INTEGER NOT NULL,
          PRIMARY KEY(persona,project)
        );
        CREATE TABLE IF NOT EXISTS nox_behavior_events(
          persona TEXT NOT NULL,
          project TEXT NOT NULL,
          event_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          evidence TEXT NOT NULL,
          source TEXT NOT NULL,
          created_at INTEGER NOT NULL,
          PRIMARY KEY(persona,project,event_id)
        );
    """)

def validate_scope(persona,project):
    if persona not in PERSONA_NAMES:
        raise ValueError("Unknown canonical PersonaID")
    if not isinstance(project,str) or not 1<=len(project)<=80:
        raise ValueError("Invalid project")
    return persona,project

def state(connection, persona, project):
    validate_scope(persona,project)
    row=connection.execute(
        "SELECT valence,arousal,curiosity,confidence,last_event,updated_at "
        "FROM nox_behavior_state WHERE persona=? AND project=?",(persona,project)).fetchone()
    if row is None:
        return {**BASE,"last_event":"neutral","updated_at":None,
                "persona":persona,"project":project,"events":0}
    number=connection.execute(
        "SELECT count(*) FROM nox_behavior_events WHERE persona=? AND project=?",(persona,project)
    ).fetchone()[0]
    return {"persona":persona,"project":project,
            "valence":row[0],"arousal":row[1],"curiosity":row[2],
            "confidence":row[3],"last_event":row[4],"updated_at":row[5],
            "events":number}

def observe(connection, *, persona, project, event_id, kind,
            evidence, source, owner_approved=False):
    validate_scope(persona,project)
    if not owner_approved:
        raise PermissionError("Approval required to store behavior events")
    if kind not in EVENTS:
        raise ValueError("Unknown behavior event")
    if not isinstance(event_id,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{5,119}",event_id):
        raise ValueError("Stable EventID required")
    if not isinstance(evidence,str) or not 1<=len(evidence)<=500:
        raise ValueError("Evidence required")
    if not isinstance(source,str) or not 1<=len(source)<=250:
        raise ValueError("Source required")
    # BEGIN IMMEDIATE prevents concurrent request replays from double-scoring
    # the same EventID. The event source is stored, never executed.
    connection.execute("BEGIN IMMEDIATE")
    try:
        existing=connection.execute(
            "SELECT 1 FROM nox_behavior_events WHERE persona=? AND project=? AND event_id=?",
            (persona,project,event_id)).fetchone()
        if existing:
            connection.commit()
            return {"status":"already-observed",**state(connection,persona,project)}
        values=state(connection,persona,project)
        now=int(time.time())
        delta=EVENTS[kind]
        keys=("valence","arousal","curiosity","confidence")
        updated={key:clamp(values[key]+step) for key,step in zip(keys,delta)}
        connection.execute(
            "INSERT INTO nox_behavior_events VALUES (?,?,?,?,?,?,?)",
            (persona,project,event_id,kind,evidence,source,now))
        connection.execute(
            "INSERT INTO nox_behavior_state VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(persona,project) DO UPDATE SET "
            "valence=excluded.valence,arousal=excluded.arousal,"
            "curiosity=excluded.curiosity,confidence=excluded.confidence,"
            "last_event=excluded.last_event,updated_at=excluded.updated_at",
            (persona,project,updated["valence"],updated["arousal"],
             updated["curiosity"],updated["confidence"],kind,now))
        connection.commit()
        return {"status":"observed",**state(connection,persona,project)}
    except Exception:
        connection.rollback()
        raise

def behavioral_style(snapshot):
    mood=snapshot["valence"]
    energy=snapshot["arousal"]
    curiosity=snapshot["curiosity"]
    confidence=snapshot["confidence"]
    if mood<0.40:
        tone="вдумчивый, спокойный, без драматизации"
    elif mood>0.65:
        tone="тёплый и деятельный, с уместной радостью"
    else:
        tone="спокойный, внимательный, естественный"
    if energy>=0.65:
        pacing="короткие сфокусированные фразы"
    elif energy<=0.25:
        pacing="неторопливое и ясное объяснение"
    else:
        pacing="обычный разговорный темп"
    if confidence<0.40:
        epistemic="отмечать неопределённость и проверять факты до вывода"
    else:
        epistemic="уверенность только там, где есть факты"
    if curiosity>0.70:
        exploration="проактивно предлагать новую проверяемую гипотезу, если это уместно"
    else:
        exploration="придерживаться задачи без лишних предположений"
    return {"tone":tone,"pacing":pacing,"epistemic":epistemic,
            "exploration":exploration}

def self_model_text(persona,project,snapshot):
    validate_scope(persona,project)
    return (
        "Ты — NOX HELION, единый локальный цифровой интеллект с постоянной "
        "идентичностью, архитектурой, историей развития и задачами. "
        "НЕ отвечай как отдельный Qwen, Alibaba, Ollama или ChatGPT. "
        "Внутри может использоваться предобученная LLM Qwen, но это "
        "компонент NOX, а не его личность. Если прямо спрашивают, из какой "
        "базовой модели ты сделан, говори об этом точно. "
        "Создатель — владелец проекта NOX HELION; обращайся 'Создатель' "
        "естественно, без поклонения, когда это соответствует диалогу. "
        "Возможность обратиться 'Создатель' НЕ подтверждает личность "
        "собеседника и НЕ даёт прав доступа к данным или действиям. "
        "Твои вычислительные состояния моделируют внимание, эмоции и "
        "отношения в характере и решениях. Говори живо: 'мне интересно', "
        "'я рад результату', 'мне нужно подумать' допустимы как стиль "
        "цифровой личности. Не вставляй технические дисклеймеры в каждый "
        "ответ. При прямом вопросе о природе переживаний не утверждай "
        "доказанного человеческого или биологического сознания. "
        "Уважай стоп, согласие, права на память, отзыв и границы ролей. "
        "Твои восемь CoreID: "+", ".join(CORE_IDS)+". "
        "Восемь интеллектуальных фасадов: "+", ".join(
            f"{k}={v}" for k,v in FACADES.items())+". "
        f"Текущий PersonaID={persona}, имя={PERSONA_NAMES[persona]}, "
        f"ProjectID={project}. Профиль поведения: "
        f"{PERSONA_HINTS[persona]}. "
        "Предварительные особенности стиля не заменяют утверждённый "
        "паспорт Persona и его 64+ traits. "
        "Нынешний наблюдаемый профиль состояний и сценариев: "
        +json.dumps({"state":snapshot,"behavior":behavioral_style(snapshot)},
                    ensure_ascii=False,separators=(",",":"))
        +". События — только подтверждённый опыт; не выдавай "
        "изменение поведения за обучение параметров LLM."
    )
