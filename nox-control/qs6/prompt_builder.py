"""prompt_builder: сборка системного промпта: «душа» + ядро памяти + (вспомнившееся, о себе, тон) + повтор главного в конце.

Повтор главного в конце нужен потому, что модель лучше держит правила, стоящие ближе к вопросу.
Бюджет токенов грубый (1 токен ~ 3 символа). При превышении режем сначала вспомнившееся, потом ядро с конца;
душа и повтор главного не режутся никогда.
"""
import os

from .core_block import est_tokens

HERE = os.path.dirname(os.path.abspath(__file__))
SOUL_PATH = os.path.join(HERE, "soul_prompt_ru.txt")
MAIN_MARK = "## Главное"


def load_soul(path=None):
    """-> (тело души без раздела «Главное», текст «Главное»)."""
    with open(path or SOUL_PATH, encoding="utf-8") as f:
        text = f.read().strip()
    body, sep, main = text.partition(MAIN_MARK)
    return body.strip(), (main.strip() if sep else "")


def build_system_prompt(core_text="", recalled=None, self_text="", style_hint="", soul_path=None, max_tokens=900):
    soul, main = load_soul(soul_path)
    recalled = [str(r).strip() for r in (recalled or []) if str(r).strip()]
    core_lines = core_text.strip().splitlines() if core_text and core_text.strip() else []
    trimmed = {"recalled": 0, "core": 0}

    def assemble():
        parts = [soul]
        mem = []
        if core_lines:
            mem.append("\n".join(core_lines))
        if recalled:
            mem.append("Вспомнилось по теме разговора:\n" + "\n".join("- " + r for r in recalled))
        if mem:
            parts.append("## Память\n" + "\n\n".join(mem))
        if self_text.strip():
            parts.append("## О себе (из данных сборки)\n" + self_text.strip())
        if style_hint.strip():
            parts.append("## Тон сейчас\n" + style_hint.strip())
        if main:
            parts.append("Главное, повторяю: " + main)
        return "\n\n".join(parts)

    text = assemble()
    while est_tokens(text) > max_tokens and recalled:
        recalled.pop(); trimmed["recalled"] += 1; text = assemble()
    while est_tokens(text) > max_tokens and core_lines:
        core_lines.pop(); trimmed["core"] += 1; text = assemble()
    return {"text": text, "tokens": est_tokens(text), "trimmed": trimmed, "over_budget": est_tokens(text) > max_tokens}


def build_messages(user_text, history=None, **kw):
    """[{"role":"system",...}] + история + вопрос. kw - аргументы build_system_prompt."""
    sysm = build_system_prompt(**kw)
    return [{"role": "system", "content": sysm["text"]}] + list(history or []) + [{"role": "user", "content": user_text}]
