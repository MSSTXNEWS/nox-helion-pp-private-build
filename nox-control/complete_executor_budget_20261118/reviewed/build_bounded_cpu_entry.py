import ast
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
base=(HERE/'owner_project_runtime_update.py').read_text();tree=ast.parse(base)
functions={'require','digest','encoded','read_regular','atomic','preimages','apply_transaction','rollback_transaction',
    'supervisor','process_identity','stop_clear','queue_idle','protected_snapshot','descendant_snapshot',
    'live_previous_descendants','wait_previous_descendants_stopped','stop_checked','start_checked','relpath',
    'acceptance_snapshot','stable_three','exact_s03','source_snapshot','start_update_checked'}
constants={'ROOT','SERVICE','CONFIG','STATE','STATUS','MAX_BYTES','SHA','IDENT','QUEUE_IDS','PROJECT_HANDLER'}
parts=['#!/usr/bin/env python3\n"""Bounded CPU policy update through the existing owner maintenance route.\n'
    'No source tree writes, task reset, model restart, or new dispatcher is introduced.\n'
    'Common helpers are frozen from '+hashlib.sha256(base.encode()).hexdigest()+'.\n"""',
    'from __future__ import annotations\nimport base64\nimport contextlib\nimport copy\nimport fcntl\nimport hashlib\n'
    'import importlib.util\nimport json\nimport math\nimport os\nfrom pathlib import Path\nimport re\nimport sqlite3\n'
    'import stat\nimport subprocess\nimport sys\nimport tempfile\nimport time']
selected=set()
for node in tree.body:
    keep=False
    if isinstance(node,ast.FunctionDef) and node.name in functions:keep=True;selected.add(node.name)
    if isinstance(node,ast.ClassDef) and node.name=='Hold':keep=True
    if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id in constants for target in node.targets):keep=True
    if keep:parts.append(ast.get_source_segment(base,node))
assert selected==functions
parts.append('SPEC = {}\ntry:\n    BUNDLE = __NOX_BUNDLE_JSON__\nexcept NameError:\n    BUNDLE = {}')
parts.append((HERE/'budget_policy_update_body.py').read_text())
raw=('\n\n'.join(parts)+'\n').encode();compile(raw,'owner_bounded_cpu_install.py','exec')
(HERE/'owner_bounded_cpu_install.py').write_bytes(raw)
print(hashlib.sha256(raw).hexdigest(),len(raw))
