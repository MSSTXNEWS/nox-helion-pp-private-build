"""Патч для qs6/prompt_builder.py: KV-кэш-дружелюбная сборка сообщений.

Проблема: build_system_prompt кладёт память, «о себе» и тон В СИСТЕМНЫЙ промпт, который стоит первым.
Он меняется каждый ход -> префикс-кэш llama.cpp сбрасывается -> вся история заново прогоняется
через prefill (на CPU-MoE это десятки секунд). Решение: системный промпт = только душа (не меняется
никогда), а изменчивое («Я сейчас» + память + тон) — короткой вставкой ПЕРЕД последним вопросом.
Тогда кэшируется душа + вся история, и считается только хвост.
Добавить в prompt_builder.py и вызывать из memory_layer.prepare вместо build_system_prompt.
"""


def build_messages_cached(user_text, history=None, soul_text="", core_text="", recalled=None,
                          self_text="", style_hint="", drive_lines=None, max_dyn_chars=6000):
    dyn = []
    now = [x for x in ([style_hint.strip()] if style_hint and style_hint.strip() else []) + list(drive_lines or [])]
    if now or (self_text and self_text.strip()):
        dyn.append("## Я сейчас\n" + "\n".join(["- " + x for x in now] +
                   (["- Тело/сервер: " + self_text.strip()] if self_text and self_text.strip() else [])))
    mem = []
    if core_text and core_text.strip():
        mem.append(core_text.strip())
    rec = [str(r).strip() for r in (recalled or []) if str(r).strip()]
    if rec:
        mem.append("Вспомнилось по теме:\n" + "\n".join("- " + r for r in rec))
    if mem:
        dyn.append("## Память\n" + "\n\n".join(mem))
    dyn_text = "\n\n".join(dyn)[:max_dyn_chars]
    msgs = [{"role": "system", "content": soul_text}] + list(history or [])
    # внутренний контекст идёт в том же user-сообщении, перед вопросом: шаблоны GLM/Qwen
    # не любят второй system посреди диалога, а в истории этот блок НЕ сохраняется
    content = ("<внутреннее_состояние>\n" + dyn_text + "\n</внутреннее_состояние>\n\n" + user_text) if dyn_text else user_text
    msgs.append({"role": "user", "content": content})
    return msgs
