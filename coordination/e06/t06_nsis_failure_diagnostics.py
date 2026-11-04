"""Read-only postmortem for an already failed disposable Windows install.

Never re-runs Setup, launches the app, removes a stage, or grants acceptance.
Reuse the original candidate/receipt/path gates and reviewed payload verifier.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys


def verify_failed_setup_identity(owner, failure: dict, evidence: dict) -> None:
    """Fail closed on immutable Setup SHA, respecting actual bridge receipt schema.

    The original LOCAL_BRIDGE candidate_gate rehashes physical Setup and
    revalidates exact source/WPF/OneHost/manifest provenance, but never emits a
    BuildID. Do not silently invent a BuildID or skip SHA verification.
    Other owner paths still MUST carry the same explicit nonempty BuildID.
    Read-only diagnostic admission does not authorize install or E07.
    """
    left = failure.get('setup_sha256')
    right = evidence.get('setup_sha256')
    owner.require(type(left) is str and type(right) is str and
                  re.fullmatch(r'[0-9a-f]{64}', right) is not None and
                  left == right,
                  'T06_NSIS_DIAGNOSTICS_SETUP_IDENTITY_HOLD')
    if owner.ON_LOCAL_BRIDGE:
        owner.require('build_id' not in failure and
                      'build_id' not in evidence,
                      'T06_NSIS_DIAGNOSTICS_SETUP_IDENTITY_HOLD')
    else:
        a = failure.get('build_id')
        b = evidence.get('build_id')
        owner.require(type(a) is str and len(a) > 0 and
                      type(b) is str and a == b,
                      'T06_NSIS_DIAGNOSTICS_SETUP_IDENTITY_HOLD')


def collect(owner, *, platform_name=None, env=None):
    env = os.environ if env is None else env
    platform_name = sys.platform if platform_name is None else platform_name
    owner.require(platform_name == 'win32' and
                  env.get('GITHUB_ACTIONS') == 'true' and
                  env.get('RUNNER_OS') == 'Windows' and
                  env.get('NOX_E07_CI_WINDOWS_DISPOSABLE') == 'YES' and
                  str(env.get('GITHUB_RUN_ID', '')).isascii() and
                  str(env.get('GITHUB_RUN_ID', '')).isdecimal(),
                  'T06_NSIS_DIAGNOSTICS_DISPOSABLE_WINDOWS_ONLY')
    failure_path = owner.OUTPUT / 'T06_INSTALLED_SMOKE.json'
    failure = owner.strict_receipt(failure_path, 'T06_NSIS_DIAGNOSTIC_RECEIPT_HOLD')
    owner.require(failure.get('reason') == 'T06_NSIS_SILENT_INSTALL_FAILED' and
                  failure.get('phase') == 'HOLD' and
                  failure.get('release_accepted') is False,
                  'T06_NSIS_DIAGNOSTICS_NO_MATCHING_FAILURE')
    evidence = owner.candidate_gate()
    verify_failed_setup_identity(owner, failure, evidence)
    local = Path(env.get('LOCALAPPDATA', ''))
    owner.require(local.is_absolute() and local.is_dir() and
                  owner.plain_parents(local, Path(local.anchor)),
                  'T06_NSIS_DIAGNOSTICS_LOCAL_ROOT_HOLD')
    install = local / 'Programs' / 'NOX HELION'
    report = {'schema': 'NOX-T06-NSIS-FAILURE-DIAGNOSTICS-v1',
              'phase': 'DIAGNOSTIC_ONLY', 'release_accepted': False,
              'original_failure': failure['reason'],
              'setup_sha256': evidence['setup_sha256'],
              'build_id': evidence['build_id'], 'slots': {}, 'verifications': []}
    for label, slot in (('stage', Path(str(install) + '.__p01_stage')),
                        ('installed', install),
                        ('previous', Path(str(install) + '.__p01_previous'))):
        safe = owner.plain_parents(slot, Path(local.anchor))
        owner.require(safe and not slot.is_symlink() and
                      not getattr(slot, 'is_junction', lambda: False)(),
                      'T06_NSIS_DIAGNOSTICS_REPARSE_HOLD')
        report['slots'][label] = {'exists': slot.exists(), 'directory': slot.is_dir()}
        if slot.is_dir():
            for name in ('payload.sha256.json', 'nox-p01-owned.txt', 'NOX.P01.Shell.exe'):
                target = slot / name
                report['slots'][label][name] = {
                    'regular': owner.regular(target),
                    'bytes': target.stat().st_size if owner.regular(target) else None}
    # Do not run either a failed app or an arbitrary residual script. Admit the
    # existing reviewer's verifier only if it matches its committed Git bytes.
    verifier_rel = 'stage/proposals/P01/C09/Installer/Verify-Payload.ps1'
    verifier = owner.ROOT / verifier_rel
    owner.require(owner.regular(verifier) and
                  owner.plain_parents(verifier, owner.ROOT),
                  'T06_NSIS_DIAGNOSTICS_VERIFIER_PATH_HOLD')
    expected = subprocess.check_output(
        ['git', '-C', str(owner.ROOT), 'show', 'HEAD:' + verifier_rel], timeout=20)
    raw = verifier.read_bytes()
    owner.require(raw == expected or raw.replace(b'\r\n', b'\n') == expected,
                  'T06_NSIS_DIAGNOSTICS_VERIFIER_BYTES_HOLD')
    report['verifier_sha256'] = hashlib.sha256(expected).hexdigest()
    # Two read-only verifier probes distinguish architecture-dependent errors.
    # The original installation result remains failed even if both probes pass.
    powershells = [('native', 'powershell.exe')]
    system = Path(env.get('SystemRoot', r'C:\Windows'))
    wow = system / 'SysWOW64/WindowsPowerShell/v1.0/powershell.exe'
    if system.is_absolute() and owner.plain_parents(wow, Path(system.anchor)) and owner.regular(wow):
        powershells.append(('x86', str(wow)))
    stage = Path(str(install) + '.__p01_stage')
    manifest = stage / 'payload.sha256.json'
    if stage.is_dir() and owner.regular(manifest):
        owner.require(owner.plain_parents(manifest, Path(local.anchor)),
                      'T06_NSIS_DIAGNOSTICS_MANIFEST_PATH_HOLD')
        for architecture, executable in powershells:
            result = owner.run([executable, '-NoProfile', '-NonInteractive',
                '-ExecutionPolicy', 'Bypass', '-File', str(verifier),
                '-Root', str(stage), '-Manifest', str(manifest)], 100)
            report['verifications'].append({'architecture': architecture, **result})
    return report


def main():
    path = Path(__file__).resolve().with_name('t06_samevm_installed_smoke.py')
    spec = importlib.util.spec_from_file_location('nox_existing_t06_smoke', path)
    if spec is None or spec.loader is None:
        raise SystemExit('T06_NSIS_DIAGNOSTICS_OWNER_MISSING')
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    report = collect(owner)
    target = owner.OUTPUT / 'T06_NSIS_FAILURE_DIAGNOSTICS.json'
    owner.require(owner.plain_parents(target, owner.ROOT),
                  'T06_NSIS_DIAGNOSTICS_OUTPUT_PATH_HOLD')
    with target.open('x', encoding='utf-8') as out:
        json.dump(report, out, ensure_ascii=True, indent=2)
        out.write('\n')
    print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
