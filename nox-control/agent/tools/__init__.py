"""Реестр инструментов агента. Формат схем: OpenAI tools. Результат инструмента всегда dict с ключом ok."""
import json, os, threading


class Tool:
    def __init__(self, name, description, parameters, func):
        self.name, self.description, self.parameters, self.func = name, description, parameters, func

    def schema(self):
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


class ToolContext:
    """Общий контекст инструментов: конфиг, рабочая ветка (worktree), очередь подтверждений, счётчики."""

    def __init__(self, cfg, workdir, approvals=None, run_id="", skills=None, codeindex=None):
        self.cfg, self.workdir, self.approvals, self.run_id = cfg, os.path.realpath(workdir), approvals, run_id
        self.skills, self.codeindex = skills, codeindex
        self.counters = {}
        self.lock = threading.Lock()

    def bump(self, key):
        with self.lock:
            self.counters[key] = self.counters.get(key, 0) + 1
            return self.counters[key]


def err(msg, **kw):
    d = {"ok": False, "error": msg}
    d.update(kw)
    return d


def need_confirm(ctx, action, detail, key=None):
    """Единый путь запроса подтверждения владельца. Возвращает dict-результат инструмента (needs_confirmation) или None, если разрешено."""
    from .approvals import Approvals
    ap = ctx.approvals or Approvals(ctx.cfg.approvals_file)
    st = ap.gate(action, detail, key=key, run_id=ctx.run_id)
    if st["state"] == "approved":
        return None
    if st["state"] == "denied":
        return {"ok": False, "error": "владелец отклонил: " + action, "denied": True, "approval_id": st["id"]}
    return {"ok": False, "needs_confirmation": True, "approval_id": st["id"], "action": action, "detail": detail,
            "error": "нужно подтверждение владельца (id %s); цикл остановится" % st["id"]}


class Registry:
    def __init__(self):
        self.tools = {}

    def add(self, tool):
        self.tools[tool.name] = tool
        return tool

    def schemas(self):
        return [t.schema() for t in self.tools.values()]

    def names(self):
        return sorted(self.tools)

    @staticmethod
    def _check(params, args):
        props = (params or {}).get("properties", {})
        for r in (params or {}).get("required", []):
            if r not in args: return "нет обязательного аргумента: " + r
        types = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
        for k, v in args.items():
            if k not in props: return "неизвестный аргумент: " + k
            t = types.get(props[k].get("type"))
            if t and (not isinstance(v, t) or (props[k].get("type") in ("integer", "number") and isinstance(v, bool))):
                return "аргумент %s должен быть %s" % (k, props[k].get("type"))
            if "enum" in props[k] and v not in props[k]["enum"]:
                return "аргумент %s: допустимо %s" % (k, props[k]["enum"])
        return None

    def call(self, name, args, ctx):
        t = self.tools.get(name)
        if not t:
            return err("нет такого инструмента: %s (есть: %s)" % (name, ", ".join(self.names())))
        if not isinstance(args, dict):
            return err("аргументы должны быть JSON-объектом")
        bad = self._check(t.parameters, args)
        if bad: return err(bad)
        try:
            r = t.func(args, ctx)
        except Exception as e:  # инструмент не должен ронять цикл
            return err("%s: %s" % (type(e).__name__, e))
        if not isinstance(r, dict):
            r = {"ok": True, "result": r}
        r.setdefault("ok", True)
        return r


def default_registry(extra=None):
    """Полный набор: shell, файлы, git, тесты, веб, браузер, поиск по коду и навыкам."""
    from . import shell, files, gitops, testing, web, browser, memory
    reg = Registry()
    for mod in (shell, files, gitops, testing, web, browser, memory):
        for t in mod.TOOLS:
            reg.add(t)
    for t in (extra or []):
        reg.add(t)
    return reg


def dumps(obj, limit):
    s = json.dumps(obj, ensure_ascii=False, default=str)
    if len(s) > limit:
        s = s[:limit] + '…[обрезано %d симв.]' % (len(s) - limit)
    return s
