"""self_map: map of modules/functions of a code tree (ast for py, headers for others)."""
import ast
import os
import registry as R


@R.register("self_map", "read", {"properties": {
    "path": {"type": "string", "default": "nox-control"}, "max_files": {"type": "integer", "default": 300}}},
    "Map python files: docstring, classes, functions, imports.")
def self_map(a):
    root = R.safe_path(a["path"], must_exist=True)
    out = []
    for d, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x not in {".git", "__pycache__"}]
        for f in sorted(fs):
            if not f.endswith(".py"):
                continue
            fp = os.path.join(d, f)
            try:
                tree = ast.parse(open(fp, encoding="utf-8").read())
            except (SyntaxError, UnicodeDecodeError, OSError) as e:
                out.append({"file": os.path.relpath(fp, R.REPO), "error": str(e)[:100]})
                continue
            doc = (ast.get_docstring(tree) or "").splitlines()
            imps = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    imps.update(x.name.split(".")[0] for x in n.names)
                elif isinstance(n, ast.ImportFrom) and n.module:
                    imps.add(n.module.split(".")[0])
            imps = sorted(imps)
            out.append({"file": os.path.relpath(fp, R.REPO), "doc": doc[0] if doc else "",
                        "classes": [n.name for n in tree.body if isinstance(n, ast.ClassDef)],
                        "functions": [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))],
                        "imports": imps})
            if len(out) >= a["max_files"]:
                return {"ok": True, "files": out, "truncated": True}
    return {"ok": True, "files": out, "truncated": False}
