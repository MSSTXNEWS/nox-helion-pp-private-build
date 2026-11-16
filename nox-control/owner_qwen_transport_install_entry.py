#!/usr/bin/env python3
"""Explicit reviewed source aliases for the ordinary finite revision installer.

The old canonical repository sources are checked, not edited. Only the two
reviewed candidate bytes replace their canonical keys in a private bundle.
"""
import base64
import hashlib
from pathlib import Path
import re
import sys
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

CANONICAL_ISSUER = 'owner_qwen_revision_install.py'
CANONICAL_STUDENT = 'qwen_student_training_entry_revision.py'
CANDIDATE_ISSUER = 'owner_qwen_transport_revision_install.py'
CANDIDATE_STUDENT = 'qwen_student_training_entry_transport_candidate.py'
ORIGINAL_ISSUER_SHA = '2dd28da0d4e90614dbc168e0d921022c2b95061d08e21b2f76394f2f6280c468'
ORIGINAL_STUDENT_SHA = '530b59ee1723c5d6279dd8523d3f090c07e984561103d567b2de2b552d1108a9'
CANDIDATE_ISSUER_SHA = '4be67c1d30d9513c96a3164c02e70056c47004922bbd3398cbc5e463f820f25d'
CANDIDATE_STUDENT_SHA = '8291638636bb03f701802c634cf8b30d077a5176c33d3658fb5cb1c92d50f235'
SCRIPTS = Path('/root/nox/scripts')


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_TRANSPORT_INSTALL_' + code)


def source(name, pin):
    require(isinstance(pin, str) and re.fullmatch('[a-f0-9]{64}', pin), 'UNREVIEWED_PIN')
    encoded = BUNDLE.get(name)
    require(isinstance(encoded, str) and 0 < len(encoded) <= 180000, 'BUNDLE_SCOPE')
    raw = base64.b64decode(encoded, validate=True)
    require(0 < len(raw) <= 131072 and hashlib.sha256(raw).hexdigest() == pin, 'SOURCE_PIN')
    compile(raw, str(SCRIPTS / name), 'exec')
    return raw


def bound_installer():
    original_issuer = source(CANONICAL_ISSUER, ORIGINAL_ISSUER_SHA)
    source(CANONICAL_STUDENT, ORIGINAL_STUDENT_SHA)
    issuer = source(CANDIDATE_ISSUER, CANDIDATE_ISSUER_SHA)
    student = source(CANDIDATE_STUDENT, CANDIDATE_STUDENT_SHA)
    old = (repr(CANONICAL_STUDENT) + ': ' + repr(ORIGINAL_STUDENT_SHA)).encode()
    new = (repr(CANONICAL_STUDENT) + ': ' + repr(CANDIDATE_STUDENT_SHA)).encode()
    require(original_issuer.count(old) == 1 and issuer == original_issuer.replace(old, new, 1),
            'ISSUER_ONLY_STUDENT_PIN_DELTA')
    private = dict(BUNDLE)
    private[CANONICAL_ISSUER] = base64.b64encode(issuer).decode('ascii')
    private[CANONICAL_STUDENT] = base64.b64encode(student).decode('ascii')
    require({key for key in BUNDLE if BUNDLE[key] != private[key]} == {CANONICAL_ISSUER, CANONICAL_STUDENT},
            'CANONICAL_ALIAS_SCOPE')
    module = types.ModuleType('_nox_reviewed_transport_installer')
    module.__file__ = str(SCRIPTS / CANONICAL_ISSUER)
    module.__dict__['__NOX_' + 'BUNDLE_JSON__'] = private
    sys.modules[module.__name__] = module
    exec(compile(issuer, module.__file__, 'exec'), module.__dict__)
    require(module.SELF == CANONICAL_ISSUER and module.STUDENT == CANONICAL_STUDENT
            and module.PINS[CANONICAL_STUDENT] == CANDIDATE_STUDENT_SHA, 'LOADED_CANONICAL_BINDING')
    return module


def main():
    return bound_installer().main()


if __name__ == '__main__':
    raise SystemExit(main())
