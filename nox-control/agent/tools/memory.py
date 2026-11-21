"""Инструменты доступа к собственной памяти агента: навыки (skills) и индекс своего кода (codeindex)."""
from . import Tool, err


def skill_search(a, ctx):
    if not ctx.skills: return err("библиотека навыков не подключена")
    hits = ctx.skills.search(a["query"], k=int(a.get("limit") or 3))
    return {"ok": True, "skills": [{"id": h["id"], "name": h["name"], "condition": h["condition"], "steps": h["steps"], "tools": h["tools"], "check": h["check"]} for h in hits]}


def code_where(a, ctx):
    if not ctx.codeindex: return err("индекс кода не подключён")
    hits = ctx.codeindex.where(a["query"], k=int(a.get("limit") or 8))
    return {"ok": True, "hits": hits}


TOOLS = [
    Tool("skill_search", "Найти в библиотеке навыков рецепт решения похожей задачи (поиск по описанию).",
         {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}, skill_search),
    Tool("code_where", "Где в моём коде X: поиск по индексу файлов, символов и docstring. Возвращает путь:строка, символ, докстринг.",
         {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}, code_where),
]
