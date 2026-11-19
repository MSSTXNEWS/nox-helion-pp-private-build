"""Owner-authenticated, read-only inspection of the live NOX chat proxy.

The host probe resolves the running nox-proxy PID from Supervisor at runtime.
It never restarts services and never prints source bytes, command-line values,
environment variables, or exception text.
"""
from __future__ import annotations

import hashlib

from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn

MAX_SOURCE_BYTES = 1_000_000

ANALYZER = r"""
import ast

MAX_SOURCE_BYTES = 1_000_000
TARGETS = ("_trim_ctx", "_build_messages", "prepare_payload")
MAX_KEYS_PER_SCOPE = 32
KEY_PATTERN = __import__("re").compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
HYDRATION_TERMS = {
    "s03": ("s03",),
    "history": ("history", "messages"),
    "dialog": ("dialog", "conversation", "thread", "session"),
    "storage": ("load", "fetch", "read", "select", "query", "store", "db", "database"),
}

def _bound(node):
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) is int):
        return -node.operand.value
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd)
            and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) is int):
        return node.operand.value
    return None

def _literal_body_keys(node):
    # Return only bounded identifier-like literal keys, never their values.
    keys = set()
    for child in ast.walk(node):
        value = None
        if isinstance(child, ast.Subscript) and isinstance(child.slice, ast.Constant):
            value = child.slice.value
        elif (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
              and child.func.attr == "get" and child.args
              and isinstance(child.args[0], ast.Constant)):
            value = child.args[0].value
        if isinstance(value, str) and KEY_PATTERN.fullmatch(value):
            keys.add(value)
    return sorted(keys)[:MAX_KEYS_PER_SCOPE]

def _hydration_presence(node):
    # Static name-presence signals only; these do not prove data flow.
    found = {key: [] for key in HYDRATION_TERMS}
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        name = (func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute) else "")
        lowered = name.lower()
        for category, terms in HYDRATION_TERMS.items():
            if any(term in lowered for term in terms):
                found[category].append(getattr(child, "lineno", 0))
    return {key: sorted(set(lines))[:32] for key, lines in found.items()}

def analyze_source(raw):
    if not isinstance(raw, bytes):
        raise ValueError("HOLD_PROXY_SOURCE_TYPE")
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("HOLD_PROXY_SOURCE_SIZE")
    try:
        text = raw.decode("utf-8")
        tree = ast.parse(text, filename="chat_proxy.py")
    except (UnicodeDecodeError, SyntaxError):
        raise ValueError("HOLD_PROXY_SOURCE_PARSE") from None

    definitions = {name: [] for name in TARGETS}
    calls = {name: [] for name in TARGETS}
    routes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in definitions and len(definitions[node.name]) < 8:
                bounds = []
                for child in ast.walk(node):
                    if isinstance(child, ast.Subscript) and isinstance(child.slice, ast.Slice):
                        lower = _bound(child.slice.lower)
                        upper = _bound(child.slice.upper)
                        if lower is not None or upper is not None:
                            bounds.append({
                                "line": getattr(child, "lineno", 0),
                                "lower": lower,
                                "upper": upper,
                            })
                definitions[node.name].append({
                    "line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "parameters": [
                        arg.arg for arg in (node.args.posonlyargs + node.args.args)
                    ][:24],
                    "constant_slice_bounds": bounds[:24],
                    "body_key_reads": _literal_body_keys(node),
                    "hydration_call_presence": _hydration_presence(node),
                })
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                func = decorator.func
                method = (func.attr.lower() if isinstance(func, ast.Attribute)
                          else None)
                if method not in ("get", "post", "put", "delete") or not decorator.args:
                    continue
                path = decorator.args[0]
                if (isinstance(path, ast.Constant) and isinstance(path.value, str)
                        and path.value.startswith("/api/nox/chat")
                        and len(path.value) <= 120 and len(routes) < 24):
                    route_calls = []
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            called = (child.func.id if isinstance(child.func, ast.Name)
                                      else child.func.attr if isinstance(child.func, ast.Attribute)
                                      else None)
                            if called in TARGETS and called not in route_calls:
                                route_calls.append(called)
                    routes.append({
                        "method": method.upper(),
                        "path": path.value,
                        "handler_line": node.lineno,
                        "context_calls": route_calls[:3],
                        "body_key_reads": _literal_body_keys(node),
                        "hydration_call_presence": _hydration_presence(node),
                    })
        elif isinstance(node, ast.Call):
            func = node.func
            name = (func.id if isinstance(func, ast.Name)
                    else func.attr if isinstance(func, ast.Attribute) else None)
            if name in calls and len(calls[name]) < 32:
                calls[name].append({"line": getattr(node, "lineno", 0)})

    return {
        "source_bytes": len(raw),
        "functions": {name: rows for name, rows in definitions.items()},
        "callsites": {name: rows for name, rows in calls.items()},
        "chat_routes": routes,
        "analysis_note": "AST-only; body keys are literal identifier names; hydration fields are call-name presence, not proof of data flow; no source text emitted",
    }
"""

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,hashlib,json,os,re,stat,subprocess
from pathlib import Path

EXPECTED='/root/nox/scripts/chat_proxy.py'
MAX_SOURCE_BYTES=1_000_000
def hold(code):
    print('NATIVE_PROXY_INSPECT='+code, flush=True)
    raise SystemExit(2)
def read_small(path, limit):
    fd=os.open(path, os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        st=os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_size>limit:
            raise ValueError('HOLD_FILE_TYPE_OR_SIZE')
        raw=f.read(limit+1)
        after=os.fstat(f.fileno())
        ident=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns)
        if len(raw)>limit or ident(st)!=ident(after):
            raise ValueError('HOLD_FILE_CHANGED')
        # procfs files report st_size=0 while still returning bounded data.
        if not path.startswith('/proc/') and len(raw)!=st.st_size:
            raise ValueError('HOLD_FILE_CHANGED')
        return raw,st
def supervisor_pid():
    r=subprocess.run(['supervisorctl','status','nox-proxy'],
                     stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL,text=True,timeout=7,check=False)
    if r.returncode!=0:
        raise ValueError('HOLD_SUPERVISOR_READ')
    m=re.fullmatch(r'nox-proxy\s+RUNNING\s+pid\s+([0-9]{1,10}),\s+uptime .+\s*',
                   r.stdout.strip())
    if not m:
        raise ValueError('HOLD_PROXY_NOT_RUNNING')
    return int(m.group(1))
def process_identity(pid):
    raw,_=read_small('/proc/%d/stat'%pid,4096)
    try:
        head,tail=raw.rsplit(b')',1)
        actual=int(head.split(b'(',1)[0].split()[-1])
        fields=tail.split()
        if actual!=pid or len(fields)<=19:
            raise ValueError()
        return int(fields[19])
    except (ValueError,IndexError):
        raise ValueError('HOLD_PID_IDENTITY') from None
def argv_has_expected_script(pid):
    raw,_=read_small('/proc/%d/cmdline'%pid,32768)
    argv=[x.decode('utf-8','strict') for x in raw.rstrip(b'\0').split(b'\0') if x]
    if not argv or not re.fullmatch(r'python(?:[0-9]+(?:\.[0-9]+)*)?',os.path.basename(argv[0])):
        return False
    cwd=os.readlink('/proc/%d/cwd'%pid)
    matches=[]
    for item in argv[1:]:
        if item.endswith('chat_proxy.py'):
            candidate=item if os.path.isabs(item) else os.path.join(cwd,item)
            if os.path.normpath(candidate)==EXPECTED:
                matches.append(item)
    return len(matches)==1
def main():
    pid=supervisor_pid()
    start_before=process_identity(pid)
    if not argv_has_expected_script(pid):
        raise ValueError('HOLD_PROXY_CMDLINE_PATH')
    path=Path(EXPECTED)
    if path.is_symlink():
        raise ValueError('HOLD_PROXY_SYMLINK')
    raw,st=read_small(EXPECTED,MAX_SOURCE_BYTES)
    if not argv_has_expected_script(pid) or process_identity(pid)!=start_before:
        raise ValueError('HOLD_PROXY_PROCESS_CHANGED')
    if supervisor_pid()!=pid:
        raise ValueError('HOLD_PROXY_PID_CHANGED')
    digest=hashlib.sha256(raw).hexdigest()
    analysis=analyze_source(raw)
    print('NATIVE_PROXY_SOURCE_META='+json.dumps({
        'path':EXPECTED,'pid':pid,'start_ticks':start_before,
        'bytes':len(raw),'sha256':digest,'owner_uid':st.st_uid,
    },separators=(',',':')),flush=True)
    print('NATIVE_PROXY_SOURCE_ANALYSIS='+json.dumps(analysis,
        ensure_ascii=False,separators=(',',':')),flush=True)
    print('NATIVE_PROXY_NOT_RESTARTED=true',flush=True)
    print('NATIVE_PROXY_READ_ONLY_COMPLETE=true',flush=True)

__ANALYZER__

try:
    main()
except SystemExit:
    raise
except Exception as exc:
    code=str(exc)
    if not code.startswith('HOLD_'):
        code='HOLD_PROXY_INSPECT_RUNTIME'
    hold(code)
PYREMOTE
"""
REMOTE = REMOTE.replace("__ANALYZER__", ANALYZER)

def probe_source_hash():
    """Exact digest of the remote program submitted to the existing owner transport."""
    return hashlib.sha256(REMOTE.encode("utf-8")).hexdigest()

if __name__ == "__main__":
    ok = False
    conn.REMOTE = REMOTE
    print("NOX_PROXY_INSPECTOR_REMOTE_SHA256=" + probe_source_hash(), flush=True)
    try:
        ok = conn.probe()
    except Exception as exc:
        code = str(exc)
        print("NOX_PROXY_SOURCE_INSPECT=" +
              (code if code.startswith("HOLD_") else "HOLD_TRANSPORT"))
    finally:
        try:
            if not conn.cleanup():
                ok = False
        except Exception:
            ok = False
    raise SystemExit(0 if ok else 2)

