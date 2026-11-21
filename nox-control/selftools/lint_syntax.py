"""lint_syntax: syntax check for .py (compile), .js (node --check), .sh (bash -n)."""
import os
import registry as R


@R.register("lint_syntax", "read", {"properties": {"paths": {"type": "array"}}, "required": ["paths"]},
            "Syntax check py/js/sh files. js needs node; if absent that file is reported blocked.")
def lint_syntax(a):
    res, bad = [], 0
    for p in a["paths"]:
        fp = R.safe_path(p, must_exist=True)
        ext = os.path.splitext(fp)[1]
        item = {"path": p}
        if ext == ".py":
            try:
                compile(open(fp, encoding="utf-8").read(), fp, "exec")
                item["ok"] = True
            except SyntaxError as e:
                item.update(ok=False, error="line %s: %s" % (e.lineno, e.msg))
        elif ext in (".js", ".mjs", ".cjs", ".sh", ".bash"):
            cmd = ["node", "--check", fp] if ext in (".js", ".mjs", ".cjs") else ["bash", "-n", fp]
            r = R.run(cmd, timeout=30)
            if r.get("missing"):
                item.update(ok=False, blocked="%s not installed" % cmd[0], need="install " + cmd[0])
            else:
                item["ok"] = r["rc"] == 0
                if r["rc"]:
                    item["error"] = r["err"][:300]
        else:
            item.update(ok=False, error="unsupported extension " + ext)
        bad += not item["ok"]
        res.append(item)
    return {"ok": bad == 0, "files": res, "bad": bad}
