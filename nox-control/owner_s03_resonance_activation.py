"""Activate only the two pinned Resonance C02 files after accepted Task 1.

The owner release bundle must inject the exact successful Task 1 report and
its independently reviewed run, job and byte digest. No host action is available
from the standalone source with these values absent.
"""

import base64
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from types import ModuleType


CONTROL = 'owner_refresh_cognition_c04.py'
TRANSFORM = 'owner_s03_resonance_context_patch.py'
TASK1_REPORT = 'resonance-context-acceptance.json'
CONTROL_PIN = 'fdd6e646c8cef1fad9a6d39afa2723375fa2e6126bf4da4989b751ffc2355de0'
TRANSFORM_PIN = '725cbc8356eef93700d8b616fd9afb6eba46dffd8215232637c93551b50792f8'
PROXY_RELEASE_SHA = 'd19027e3d12980baa619474e633c5cd452d1570d8c5549b1421fc8041e2c4064'
PROXY_RELEASE_RUN = 44607432477
PROXY_RELEASE_JOB = 135854768793
SHA = re.compile(r'[a-f0-9]{64}')


def require(condition, code):
    if not condition:
        raise RuntimeError('HOLD_S03_RESONANCE_ACTIVATION_' + code)


def digest(data):
    return sha256(data).hexdigest()


def review_report(raw, witness):
    """Bind the verified owner run without accepting a generic workflow PASS."""
    require(isinstance(witness, dict)
            and set(witness) == {'run_id', 'job_id', 'report_sha256'}
            and all(type(witness[key]) is int and witness[key] > 0 for key in ('run_id', 'job_id'))
            and isinstance(witness['report_sha256'], str) and SHA.fullmatch(witness['report_sha256']),
            'TASK1_WITNESS')
    require(digest(raw) == witness['report_sha256'], 'TASK1_REPORT_PIN')
    report = json.loads(raw)
    require(isinstance(report, dict)
            and report.get('kind') == 'resonance_context_acceptance_v1'
            and report.get('state') == 'TWO_TURN_CONTEXT_ACCEPTED'
            and type(report.get('posts')) is int and report['posts'] == 2
            and report.get('proxy_sha256') == PROXY_RELEASE_SHA
            and all(report.get(key) is True for key in (
                'owner_authenticated', 'context_recall', 'dialog_readback')),
            'TASK1_NOT_ACCEPTED')
    identity = report.get('proxy_identity')
    require(isinstance(identity, list) and len(identity) == 2
            and all(type(value) is int and value > 1 for value in identity), 'TASK1_PROXY_IDENTITY')
    return tuple(identity)


def load_pinned(name, raw, expected):
    require(digest(raw) == expected, 'CODE_PIN')
    module = ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(raw, name, 'exec'), module.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def activate(bundle, witness):
    require(isinstance(bundle, dict) and set(bundle) == {CONTROL, TRANSFORM, TASK1_REPORT}, 'BUNDLE')
    require(all(isinstance(value, str) and 0 < len(value) <= 512 * 1024
                for value in bundle.values()), 'BUNDLE_BYTES')
    try:
        raw = {name: base64.b64decode(value, validate=True) for name, value in bundle.items()}
    except ValueError:
        raise RuntimeError('HOLD_S03_RESONANCE_ACTIVATION_BUNDLE_ENCODING') from None
    old_proxy = review_report(raw[TASK1_REPORT], witness)

    control = load_pinned('_nox_resonance_s03_control', raw[CONTROL], CONTROL_PIN)
    try:
        patch = load_pinned('_nox_resonance_s03_patch', raw[TRANSFORM], TRANSFORM_PIN)
        try:
            require(set(patch.PREIMAGES) == {patch.CONTEXT, patch.PROXY}
                    and patch.PREIMAGES[patch.PROXY] == PROXY_RELEASE_SHA, 'PATCH_SCOPE')
            # Put the context module in place first while the one proxy is down.
            control.PREIMAGE = {name: patch.PREIMAGES[name] for name in (patch.CONTEXT, patch.PROXY)}
            control.KEEP = {name: pin for name, pin in control.KEEP.items() if name not in control.PREIMAGE}
            control.KEEP.update(patch.RETAIN)
            control.STOP += (Path('/root/nox/state/MEMORY_STOP.flag'),)
            original_ready = control.ready

            def ready(proxy, *, previous=None):
                observed = original_ready(proxy, previous=previous)
                # The first ready check runs inside the C04 exclusive lease.
                if previous is None:
                    require(observed == old_proxy, 'TASK1_PROXY_GENERATION_CHANGED')
                return observed

            control.ready = ready
            preimages = control.current_patch_preimages()
            payloads = {name: patch.transform(name, preimages[name]) for name in control.PREIMAGE}
            result = control.activate(payloads=payloads, sha256=patch.POSTIMAGES)
            require(tuple(result['proxy_previous_generation']) == old_proxy
                    and tuple(result['proxy_new_generation']) != old_proxy
                    and result['proxy_http_200'] is True
                    and result['protected_resonance_still_requires_auth'] is True
                    and result['files_sha256'] == patch.POSTIMAGES
                    and result['model_restarted'] is False and result['other_services_restarted'] is False,
                    'INSTALL_READBACK')
            return {**result, 'schema': 'NOX_NATIVE_S03_RESONANCE_CONTEXT_RELEASE_V1',
                    'previous_release_run': PROXY_RELEASE_RUN, 'previous_release_job': PROXY_RELEASE_JOB,
                    'task1_run_id': witness['run_id'], 'task1_job_id': witness['job_id'],
                    'task1_report_sha256': witness['report_sha256'], 's03_context_updated': True,
                    'live_s03_acceptance_verified': False}
        finally:
            sys.modules.pop(patch.__name__, None)
    finally:
        sys.modules.pop(control.__name__, None)


def main():
    try:
        result = activate(globals().get('__NOX_BUNDLE_JSON__'), globals().get('__NOX_TASK1_ACCEPTANCE_PIN__'))
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as error:
        code = str(error)
        result = {'state': 'HOLD', 'reason': code if re.fullmatch(r'HOLD_[A-Z0-9_]{1,100}', code)
                  else 'HOLD_S03_RESONANCE_ACTIVATION_RUNTIME'}
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 's03_resonance_context_release', 'data': result},
          sort_keys=True, separators=(',', ':')), flush=True)
    if result.get('state') == 'HOLD':
        return 2
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
