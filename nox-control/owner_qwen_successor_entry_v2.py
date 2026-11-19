#!/usr/bin/env python3
"""Pin the finite successor issuer and its explicit native source aliases."""
import base64
import hashlib
import sys
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ISSUER = 'owner_qwen_successor_install_v2.py'
NATIVE_ISSUER = 'owner_qwen_revision_install.py'
ISSUER_SHA = 'd562ff23fcf21fb0873a93e6e68b23f0dffa87db07e3fe309bed3e750d0080e6'


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_QWEN_SUCCESSOR_ENTRY_' + code)


def prepared():
    encoded = BUNDLE.get(ISSUER)
    require(isinstance(encoded, str) and 0 < len(encoded) <= 180000, 'BUNDLE_SCOPE')
    raw = base64.b64decode(encoded, validate=True)
    require(0 < len(raw) <= 131072 and hashlib.sha256(raw).hexdigest() == ISSUER_SHA, 'ISSUER_PIN')
    private = dict(BUNDLE)
    private[NATIVE_ISSUER] = base64.b64encode(raw).decode('ascii')
    value = types.ModuleType('_nox_successor_finite_issuer')
    value.__file__ = '/root/nox/scripts/' + NATIVE_ISSUER
    value.__dict__['__NOX_' + 'BUNDLE_JSON__'] = private
    sys.modules[value.__name__] = value
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    require(value.SELF == NATIVE_ISSUER and len(value.CANDIDATES) == 9
            and len(value.UTILITIES) == 3, 'ISSUER_CONTRACT')
    required = {*value.CANDIDATES, *value.UTILITIES, NATIVE_ISSUER}
    require(len(required) == 13 and required <= set(private), 'DEPENDENCY_CLOSURE')
    value.BUNDLE = {name: private[name] for name in required}
    assets = value.assets()
    require(len(assets) == 13 and assets[NATIVE_ISSUER] == raw, 'NATIVE_ALIAS_CLOSURE')
    return value


def main():
    return prepared().main()


if __name__ == '__main__':
    raise SystemExit(main())
