"""Freeze a standalone update entry from audited installer helpers and narrow body."""
import ast
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
base_path=HERE/'owner_complete_executor_install.py'
source=base_path.read_text();tree=ast.parse(source)
functions={
    'require','digest','encoded','read_regular','atomic','preimages','apply_transaction',
    'rollback_transaction','supervisor','process_identity','stop_clear','queue_idle',
    'protected_snapshot','descendant_snapshot','live_previous_descendants',
    'wait_previous_descendants_stopped','stop_checked','start_checked','relpath',
    'package_changes','sandbox_preflight','stable_three','acceptance_snapshot',
}
constants={'ROOT','SERVICE','CONFIG','STATE','STATUS','MAX_BYTES','SHA','IDENT','QUEUE_IDS',
           'PROJECT_HANDLER','PREFLIGHT_BASE','PREFLIGHT_PATCH','PREFLIGHT_TEST'}
parts=['#!/usr/bin/env python3\n"""Pinned incremental runtime update. No source reseed or direct queue writes.\n'
       'Only sandbox/model modules, their exact config pins and four retry rows change.\n'
       'Copied helpers originate from installer SHA256 '+hashlib.sha256(source.encode()).hexdigest()+'.\n"""']
selected=set()
for node in tree.body:
    use=isinstance(node,(ast.Import,ast.ImportFrom))
    if isinstance(node,ast.FunctionDef) and node.name in functions:use=True;selected.add(node.name)
    if isinstance(node,ast.ClassDef) and node.name=='Hold':use=True
    if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id in constants for target in node.targets):use=True
    if use:
        text=ast.get_source_segment(source,node)
        if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='PREFLIGHT_TEST' for target in node.targets):
            fixture=ast.literal_eval(node.value)
            assert fixture.count(b'import unittest\n')==1 and fixture.count(b'self.assertEqual(source.value(), 2)')==1
            fixture=fixture.replace(b'import unittest\n',b'import unittest\nfrom pathlib import Path\n')
            fixture=fixture.replace(b'self.assertEqual(source.value(), 2)',
                b'self.assertEqual(source.value(), 2)\n        self.assertEqual(str(Path(__file__).parent), "/work/project/source")\n        self.assertEqual(str(Path(__file__).parents[3]), "/")')
            text='PREFLIGHT_TEST = '+repr(fixture)
        parts.append(text)
assert selected==functions
parts.insert(4,'import contextlib\nimport math\nimport sqlite3\nimport urllib.request')
parts.append('SPEC = {}\ntry:\n    BUNDLE = __NOX_BUNDLE_JSON__\nexcept NameError:\n    BUNDLE = {}')
parts.append((HERE/'runtime_update_body.py').read_text())
raw=('\n\n'.join(parts)+'\n').encode();compile(raw,'owner_project_runtime_update.py','exec')
(HERE/'owner_project_runtime_update.py').write_bytes(raw)
print(hashlib.sha256(raw).hexdigest(),len(raw))
