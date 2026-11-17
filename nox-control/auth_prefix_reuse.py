import ast, contextlib, ipaddress, json, os, re, socket, subprocess, sys, time
from pathlib import Path
import owner_cp55_cipher as core
REPOSITORY=Path(__file__).resolve().parents[1]
AUTH_PREFIX_SHA="095508ea245b95ac9d1623c5919de551a5c67ec47e2f561a4b3eafad800d6728"
SSH_HELPER_SHA="0d38365146c6e580dbcdc04f4b7c9a973bacd2713adcbff4cf39eb334765969b"
HOST_PIN="SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc"
def authentication_namespace():
    path = REPOSITORY / 'nox-control/owner_native_operator.py'
    source = path.read_text()
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_native']
    core.require(len(functions) == 1, 'AUTH_FUNCTION')
    fn = functions[0]
    anchors = [n for n in fn.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'payload' for t in n.targets)]
    core.require(len(anchors) == 1, 'AUTH_PREFIX_ANCHOR')
    prefix = ''.join(source.splitlines(keepends=True)[fn.lineno - 1:anchors[0].lineno - 1])
    core.require(core.sha(prefix.encode()) == AUTH_PREFIX_SHA, 'AUTH_PREFIX_PIN')
    helper = REPOSITORY / 'nox_runpod/teacher_mesh/v51/ephemeral_ssh_probe.py'
    core.require(core.sha(helper.read_bytes()) == SSH_HELPER_SHA, 'SSH_HELPER_PIN')
    ns = {'__file__': str(path), 'sys': sys, 'Path': Path, 'os': os, 'ipaddress': ipaddress,
          'socket': socket, 'subprocess': subprocess, 'json': json, 'time': time,
          're': re, 'INSTANCE': 60509551, 'PIN': HOST_PIN, 'MASTER': None}
    # Exact prefix ends before payload selection. Only this added return is new.
    exec(compile(prefix + '    return common, host, s\n', '<pinned-owner-authentication>', 'exec'), ns)
    return ns

def cleanup(ns):
    if ns and ns.get('MASTER'):
        with contextlib.suppress(Exception):
            subprocess.run(ns['MASTER'], capture_output=True, timeout=8)
    sys.path.insert(0, str(REPOSITORY))
    from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as helper
    good = helper.cleanup()
    with contextlib.suppress(OSError):
        helper.KEY.unlink()
    return good
