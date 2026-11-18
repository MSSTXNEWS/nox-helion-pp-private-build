"""Import-ABI adapter for the unchanged successful owner lifecycle.

Existing proxy and model-reference helper are transformed by exact SHA/size
CAS. Automatic rollback uses owned backups in the inherited transaction.
"""
import hashlib

import context_source_transform as context
import model_reference_wording_transform as wording

TRANSFORMS = {
    'chat_proxy.py': {
        'before_sha256': '30207a85eed6c87df4a6ee4dd8614442a62622eefacac7fae822b23ad385b343',
        'before_bytes': 103831,
        'after_sha256': '1b468ebda8cdae0dce3fd1b9df4f7def64c56d708796b05e5bd7f88fbc76af62',
        'after_bytes': 100684,
    },
    'owner_model_reference_binding.py': dict(wording.PINS),
}


def transform(name, raw, rollback=False):
    if name not in TRANSFORMS or rollback is not False:
        raise ValueError('HOLD_CONTEXT_TRANSFORM_SCOPE_OR_EXPLICIT_ROLLBACK')
    pins = TRANSFORMS[name]
    if len(raw) != pins['before_bytes'] or hashlib.sha256(raw).hexdigest() != pins['before_sha256']:
        raise ValueError('HOLD_CONTEXT_INSTALL_PREIMAGE')
    candidate = context.transform(raw) if name == 'chat_proxy.py' else wording.transform(raw)
    if len(candidate) != pins['after_bytes'] or hashlib.sha256(candidate).hexdigest() != pins['after_sha256']:
        raise ValueError('HOLD_CONTEXT_INSTALL_POSTIMAGE')
    compile(candidate, name, 'exec')
    return candidate
