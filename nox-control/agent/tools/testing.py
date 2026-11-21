"""run_tests: python3 -m unittest в рабочей ветке (в песочнице), результат структурой."""
import os, re, shlex
from . import Tool, err
from . import shell

ALLOWED = re.compile(r"^python3? -m unittest( |$)")


def parse_unittest(text):
    ran = re.findall(r"^Ran (\d+) tests? in", text, re.M)
    n = int(ran[-1]) if ran else 0
    m = re.search(r"^(OK|FAILED)(?: \((.*?)\))?", text, re.M)
    failures = errors = skipped = 0
    if m and m.group(2):
        for k, v in re.findall(r"(failures|errors|skipped)=(\d+)", m.group(2)):
            if k == "failures": failures = int(v)
            elif k == "errors": errors = int(v)
            else: skipped = int(v)
    ok = bool(m) and m.group(1) == "OK" and n > 0
    return {"ran": n, "failures": failures, "errors": errors, "skipped": skipped, "ok": ok}


def run_tests(workdir, cfg, cmd=None, cwd_rel=None, timeout=None):
    cmd = cmd or cfg.test_cmd
    cwd_rel = cfg.test_cwd if cwd_rel is None else cwd_rel
    if not ALLOWED.match(cmd): return err("run_tests запускает только python3 -m unittest ...")
    cwd = os.path.realpath(os.path.join(workdir, cwd_rel))
    if cwd != workdir and not cwd.startswith(workdir + os.sep): return err("cwd вне рабочей ветки")
    if not os.path.isdir(cwd): return err("нет каталога тестов: " + cwd_rel)
    an = shell.analyze(cmd, workdir, cwd)
    if an["verdict"] != "ok": return err("команда тестов не прошла проверку: " + "; ".join(an["reasons"]))
    r = shell.execute(shlex.split(cmd), cwd, cfg, timeout or cfg.test_timeout, 20000)
    if r.get("blocked") or "stdout" not in r: return r
    text = r["stderr"] + "\n" + r["stdout"]
    res = parse_unittest(text)
    res.update(cmd=cmd, cwd=cwd_rel, exit_code=r["exit_code"], timed_out=r["timed_out"], tail=text.strip()[-3000:], seconds=r["seconds"])
    res["ok"] = res["ok"] and r["exit_code"] == 0 and not r["timed_out"]
    if not res["ok"]: res["error"] = "тесты не зелёные" if res["ran"] else "тесты не запустились или 0 тестов"
    return res


def tool_run_tests(a, ctx):
    return run_tests(ctx.workdir, ctx.cfg, a.get("cmd"), a.get("cwd"), a.get("timeout"))


TOOLS = [Tool("run_tests", "Запустить тесты (python3 -m unittest ...) в рабочей ветке. По умолчанию команда из NOX_AGENT_TEST_CMD. Возвращает ok/ran/failures/errors/tail.",
              {"type": "object", "properties": {"cmd": {"type": "string"}, "cwd": {"type": "string"}, "timeout": {"type": "number"}}}, tool_run_tests)]
