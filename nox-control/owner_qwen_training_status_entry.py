#!/usr/bin/env python3
"""Install the dedicated Qwen reader through the exact existing status installer.

Only installed1688 or this exact reader is an accepted preimage. The existing
91df hooks, stream and inventory remain byte-identical. The observer dependency
is either absent or its exact reviewed bytes. A sealed context is mandatory;
the reader can observe only a cryptographically linked, reviewed descendant.
"""
import base64
import hashlib
import json
import re
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ENTRY_SHA = '9b938d80a8e8769467b219f0497f00897b4cfe103cfcc693c6a70fea28491301'
PREVIOUS_STATUS_SHA = '1688fc70b8663434beed02b6d4488ca8e5f636af71aa8e5498e5606f2b69751a'
STATUS_SHA = '56ac00ee986932524fe61b996b6edde651419dcc0da028d8b6a56f342be58ae8'
OBSERVER_SHA = 'f2dc6c155b682bdeb663bc383f1aa1db70895f815939099690d898262a3d986a'


def source(name, pin):
    raw = base64.b64decode(BUNDLE.get(name + '.py', ''), validate=True)
    if not raw or len(raw) > 1_000_000 or hashlib.sha256(raw).hexdigest() != pin:
        raise RuntimeError('HOLD_QWEN_STATUS_INSTALL_BUNDLE_PIN')
    return raw


def configure():
    original = source('owner_training_status_entry', ENTRY_SHA)
    reader = source('owner_qwen_training_status', STATUS_SHA)
    observer = source('owner_qwen_training_observe', OBSERVER_SHA)
    module = types.ModuleType('_nox_qwen_status_exact_installer')
    exec(compile(original, '<exact-immutable-status-installer>', 'exec'), module.__dict__)
    if module.STATUS_SHA != PREVIOUS_STATUS_SHA:
        raise RuntimeError('HOLD_QWEN_STATUS_INSTALLER_PREIMAGE')
    module.STATUS_SHA = STATUS_SHA
    module.PREVIOUS_STATUS_SHA = PREVIOUS_STATUS_SHA
    module.LAST_INSTALLED_STATUS_SHA = PREVIOUS_STATUS_SHA
    module.BUNDLE = {**BUNDLE, 'owner_training_status.py': base64.b64encode(reader).decode('ascii')}
    old_dependencies, old_sources, old_guards = module.dependencies, module.sources, module.guards

    def dependencies():
        values = old_dependencies()
        # The dependency is checked in memory before any target mutation. The
        # live import reads its newly installed, separately pinned native file.
        values[2]._OBSERVER_SOURCE_BYTES = observer
        return values

    def sources(deploy, status, binding, context):
        rows = old_sources(deploy, status, binding, context)
        path = deploy.plain(deploy.SCRIPTS / 'owner_qwen_training_observe.py')
        old = deploy.read(path) if path.exists() else None
        if old is not None and hashlib.sha256(old).hexdigest() != OBSERVER_SHA:
            raise RuntimeError('HOLD_QWEN_STATUS_OBSERVER_PREIMAGE')
        compile(observer, str(path), 'exec')
        rows.append({'path': path, 'old': old, 'new': observer, 'changed': old != observer})
        return rows

    def guards(deploy, evidence):
        values = old_guards(deploy, evidence)
        for relative in (
            'scripts/qwen_student_training_entry.py', 'scripts/owner_qwen_training_contract.py',
            'scripts/owner_qwen_memfd.py', 'scripts/owner_qwen_corpus.py', 'scripts/qwen35_9b_manifest.json',
            'scripts/run_train_volta_t866u.sh', 'state/owner_training_admission.json',
            'state/owner_qwen_install_6907283384.json',
        ):
            path = deploy.plain(deploy.ROOT / relative)
            values[str(path)] = hashlib.sha256(deploy.read(path)).hexdigest()
        return values

    module.dependencies, module.sources, module.guards = dependencies, sources, guards
    return module


def main():
    return configure().main()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc)
        if not re.fullmatch('(?:HOLD|WAIT)_[A-Z0-9_]+', reason):
            reason = 'HOLD_QWEN_STATUS_INSTALL_' + type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_training_status_hold',
              'data': {'reason': reason}}), flush=True)
        raise SystemExit(2)
