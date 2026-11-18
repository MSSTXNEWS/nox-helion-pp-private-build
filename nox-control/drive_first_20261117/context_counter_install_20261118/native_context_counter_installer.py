"""Three-file context and model-reference update using the verified proxy-only lifecycle.

Only nox-proxy is stopped/started. Existing maintenance/STOP/idle/service/CAS
guards remain active. The new helper must be absent. Existing unknown files
are never adopted. No model/common/queue configuration/history/S03 changes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

import native_v24_dialog_installer as base
import native_v24_dialog_transform as source
from context_install_artifacts import ARTIFACTS, ARTIFACT_PINS

SOURCE_ORDER = ('owner_model_reference_binding.py', 'chat_proxy.py')
NEW_ORDER = ('owner_context_budget.py',)
OLD_PROXY = {'pid': 3648425, 'start_ticks': 175058217,
             'argv_sha256': 'da23c227363412f8a37b8bd043594d7b087c4fc9441af97e10f63bc32cf0e60f',
             'exe': '/usr/bin/python3.12', 'cwd': '/root/nox/scripts',
             'config_sha256': 'ddec2af7e644f9bfae231ae47d1975542b9eddf6f2bee1d2e14a0ff34db3c18b'}
_OriginalTransaction = base.FileTransaction
_original_metadata = base.metadata_preflight
_original_service_identity = base.service_identity
_original_command = base.command
_original_save_receipt = base.save_receipt
_stop_attempted = False
_transaction = None
_configured = False


def target(name):
    if name == NEW_ORDER[0]:
        return base.SCRIPTS / name
    raise base.Hold('HOLD_NEW_ARTIFACT_SCOPE')


def absent(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    return False


def directory_identity(path):
    base.checked_directory(path)
    info = path.lstat()
    return {key: getattr(info, 'st_' + key) for key in ('dev', 'ino', 'mode', 'uid', 'gid')}


def metadata_preflight():
    result = _original_metadata()
    for name in NEW_ORDER:
        path = target(name)
        try:
            base.checked_directory(path.parent)
            missing = absent(path)
        except OSError:
            missing = False
        reasons = [] if missing else ['NEW_TARGET_MUST_BE_ABSENT']
        result['paths'].append({'path': str(path), 'kind': 'new bounded artifact', 'required': True,
                                'expected_absent': True, 'blockers': reasons})
        if reasons:
            result['blockers'].append({'path': str(path), 'reasons': reasons})
    return result


def service_identity(allow_stopped=False):
    value = _original_service_identity(allow_stopped=allow_stopped)
    if not _stop_attempted:
        process = value['process']
        if process is None or any(process.get(key) != OLD_PROXY[key]
                                  for key in ('pid', 'start_ticks', 'argv_sha256', 'exe', 'cwd')):
            raise base.Hold('HOLD_EXPECTED_CURRENT_PROXY_LIFETIME')
        if value['config']['sha256'] != OLD_PROXY['config_sha256']:
            raise base.Hold('HOLD_EXPECTED_CURRENT_PROXY_CONFIG')
    return value


def command(args, timeout=12):
    global _stop_attempted
    if args == ['supervisorctl', 'stop', base.SERVICE]:
        # The unchanged run() already rechecked owner_idle, lease, source CAS
        # and the exact service lifetime immediately before this command.
        _stop_attempted = True
    return _original_command(args, timeout)


class BindingTransaction(_OriginalTransaction):
    def __init__(self, request, rollback=False):
        global _transaction
        if rollback:
            raise base.Hold('HOLD_EXPLICIT_ROLLBACK_REQUIRES_INSTALL_RECEIPT')
        super().__init__(request, rollback=False)
        self.stage = base.SCRIPTS / ('.owner-context-budget-' + request)
        self.backup = self.stage / 'originals'
        self.new_stage = {}
        self.new_stage_metadata = {}
        self.new_installed_metadata = {}
        self.new_created = []
        self.new_link_attempted = []
        self.new_removed = []
        self.source_stage_metadata = {}
        self.source_restored = []
        self.parents = {}
        _transaction = self

    def _prepare(self):
        for name in NEW_ORDER:
            if not absent(target(name)):
                raise base.Hold('HOLD_NEW_ARTIFACT_ALREADY_PRESENT')
            raw, pins = ARTIFACTS[name], ARTIFACT_PINS[name]
            if len(raw) != pins['bytes'] or base.digest(raw) != pins['sha256']:
                raise base.Hold('HOLD_NEW_ARTIFACT_EMBEDDED_PIN')
            if name.endswith('.py'):
                compile(raw, name, 'exec')
            else:
                json.loads(raw)
            self.parents[target(name).parent] = directory_identity(target(name).parent)
        super()._prepare()
        for name in SOURCE_ORDER:
            raw, info = base.stable_read(self.stage / name)
            if raw != self.prepared[name]:
                raise base.Hold('HOLD_SOURCE_STAGE_PIN')
            self.source_stage_metadata[name] = info
        for name in NEW_ORDER:
            path = self.stage / ('new-' + name)
            self.new_stage[name] = path
            base.write_new(path, ARTIFACTS[name], 0o600, os.geteuid(), os.getegid())
            self.new_stage_metadata[name] = base.stable_read(path)[1]
        base.sync_directory(self.stage)
        self._verify_new_stages()

    def _verify_parents(self):
        for path, expected in self.parents.items():
            if directory_identity(path) != expected:
                raise base.Hold('HOLD_NEW_ARTIFACT_PARENT_CHANGED')

    def _verify_new_stages(self):
        self._verify_parents()
        for name, path in self.new_stage.items():
            if name in self.new_created:
                continue
            raw, meta = base.stable_read(path)
            if raw != ARTIFACTS[name] or meta != self.new_stage_metadata[name]:
                raise base.Hold('HOLD_NEW_ARTIFACT_STAGE_CHANGED')

    def _owned_new(self, name):
        raw, info = base.stable_read(target(name))
        origin = self.new_stage_metadata[name]
        if raw != ARTIFACTS[name] or any(info[k] != origin[k] for k in ('dev', 'ino', 'uid', 'gid', 'mode')):
            raise base.Hold('HOLD_NEW_ARTIFACT_OWNERSHIP_DRIFT')
        if stat.S_IMODE(info['mode']) != 0o600:
            raise base.Hold('HOLD_NEW_ARTIFACT_MODE')
        # A partial link/unlink transaction may still have the staged hardlink;
        # its exact owned identity must then match before rollback can unlink.
        links = target(name).lstat().st_nlink
        if links == 2:
            staged = self.new_stage[name].lstat()
            if (staged.st_dev, staged.st_ino) != (info['dev'], info['ino']):
                raise base.Hold('HOLD_NEW_ARTIFACT_LINK_DRIFT')
        elif links != 1:
            raise base.Hold('HOLD_NEW_ARTIFACT_LINK_DRIFT')
        expected = self.new_installed_metadata.get(name)
        if expected is not None and info != expected:
            raise base.Hold('HOLD_NEW_ARTIFACT_METADATA_DRIFT')
        return info

    def _verify_new_current(self):
        self._verify_parents()
        for name in NEW_ORDER:
            if name in self.new_created and name not in self.new_removed:
                self._owned_new(name)
            elif not absent(target(name)):
                raise base.Hold('HOLD_NEW_ARTIFACT_APPEARED')

    def verify_current(self, expected, identity=False):
        super().verify_current(expected, identity=identity)
        for name in self.replaced:
            if name not in self.source_restored and expected[name] == self.prepared[name]:
                self._owned_source(name)
        self._verify_new_current()

    def verify_backups(self):
        super().verify_backups()
        for name, expected in self.source_stage_metadata.items():
            if name not in self.replaced:
                raw, info = base.stable_read(self.stage / name)
                if raw != self.prepared[name] or info != expected:
                    raise base.Hold('HOLD_SOURCE_STAGED_IDENTITY_DRIFT')
        self._verify_new_stages()

    def _owned_source(self, name):
        raw, info = base.stable_read(base.SCRIPTS / name)
        expected = self.source_stage_metadata[name]
        if raw != self.prepared[name] or any(info[k] != expected[k] for k in ('dev', 'ino', 'uid', 'gid', 'mode', 'size')):
            raise base.Hold('HOLD_SOURCE_POSTIMAGE_OWNERSHIP_DRIFT')
        return info

    def replace(self, quiescent):
        self.verify_current(self.original, identity=True)
        self.verify_backups()
        for name in NEW_ORDER:
            quiescent()
            self.verify_backups()
            self._verify_new_current()
            self.new_link_attempted.append(name)
            # Atomic no-clobber creation; an unexpected target is never replaced.
            os.link(self.new_stage[name], target(name), follow_symlinks=False)
            self.new_created.append(name)
            self._owned_new(name)
            os.unlink(self.new_stage[name])
            base.sync_directory(target(name).parent)
            base.sync_directory(self.stage)
            self.new_installed_metadata[name] = self._owned_new(name)
            if target(name).lstat().st_nlink != 1:
                raise base.Hold('HOLD_NEW_ARTIFACT_FINAL_LINKS')
        super().replace(quiescent)
        self._verify_new_current()

    def undo(self, quiescent):
        # Restore source while the proxy is stopped; remove only the helper
        # provably created by this request. Its original path was absent.
        expected = {name: self.prepared[name] if name in self.replaced else self.original[name]
                    for name in SOURCE_ORDER}
        self.verify_current(expected)
        self.verify_backups()
        for name in reversed(self.replaced):
            quiescent()
            self.verify_backups()
            self._owned_source(name)
            if base.stable_read(self.backup / name)[0] != self.original[name]:
                raise base.Hold('HOLD_ROLLBACK_BACKUP_DRIFT')
            info = self.metadata[name]
            restore = self.stage / (name + '.restore')
            base.write_new(restore, self.original[name], info['mode'], info['uid'], info['gid'])
            self._owned_source(name)
            os.replace(restore, base.SCRIPTS / name)
            self.source_restored.append(name)
            base.sync_directory(base.SCRIPTS)
        self.verify_current(self.original)
        for name in reversed(self.new_created):
            quiescent()
            self.verify_backups()
            self._owned_new(name)
            os.unlink(target(name))
            self.new_removed.append(name)
            base.sync_directory(target(name).parent)
        self._verify_new_current()

    def extras_receipt(self):
        rows = {}
        for name in NEW_ORDER:
            path = target(name)
            row = {'path': str(path), 'expected': ARTIFACT_PINS[name], 'originally_absent': True,
                   'link_attempted': name in self.new_link_attempted, 'created_by_request': name in self.new_created,
                   'removed_by_rollback': name in self.new_removed}
            try:
                if absent(path):
                    row['after'] = {'absent': True}
                else:
                    raw, info = base.stable_read(path)
                    row['after'] = {'sha256': base.digest(raw), 'bytes': len(raw), 'dev': info['dev'], 'ino': info['ino'],
                                    'mode': oct(stat.S_IMODE(info['mode'])), 'uid': info['uid'], 'gid': info['gid'],
                                    'nlink': path.lstat().st_nlink}
            except (OSError, base.Hold):
                row['after'] = {'unknown': True}
            rows[name] = row
        return rows


def finalize_report(report):
    report.update(schema='NOX_CONTEXT_COUNTER_PROXY_INSTALL_V1', s03_source_modified=False,
                  source_files_modified=list(SOURCE_ORDER), new_artifact_paths=[str(target(n)) for n in NEW_ORDER],
                  new_services=0, model_calls=0, model_reloads=0, counter_resets=0, queue_resets=0,
                  history_resets=0, s03_reset_or_migration_requested=False,
                  changed_context_counter_path_runtime_qa='PENDING_TARGETED_USE',
                  exact_final_model_input_token_fit='NOT_OBSERVED',
                  optional_o2_pending_is_blocker=False,
                  inherited_process_metadata_reader='Bounded environ read for Supervisor service identity; values never exported')
    if _transaction is not None:
        report['new_artifacts'] = _transaction.extras_receipt()
        report['source_postimage_stage_identity'] = {
            name: {key: info[key] for key in ('dev', 'ino', 'uid', 'gid', 'mode', 'size')}
            for name, info in _transaction.source_stage_metadata.items()}
        report['source_restored_by_request'] = list(_transaction.source_restored)
    if report.get('files_after'):
        old = all(report['files_after'][n]['sha256'] == source.TRANSFORMS[n]['before_sha256'] for n in SOURCE_ORDER)
        new = all(report['files_after'][n]['sha256'] == source.TRANSFORMS[n]['after_sha256'] for n in SOURCE_ORDER)
        extras = report.get('new_artifacts', {})
        extras_new = all(extras.get(n, {}).get('after', {}).get('sha256') == ARTIFACT_PINS[n]['sha256']
                         and extras.get(n, {}).get('after', {}).get('nlink') == 1
                         and extras.get(n, {}).get('after', {}).get('mode') == '0o600'
                         and extras.get(n, {}).get('after', {}).get('uid') == os.geteuid()
                         and extras.get(n, {}).get('after', {}).get('gid') == os.getegid() for n in NEW_ORDER)
        extras_absent = all(extras.get(n, {}).get('after', {}).get('absent') is True for n in NEW_ORDER)
        report['installed'] = True if new and extras_new else False if old and extras_absent else None
        if report.get('completed') is True and report['installed'] is not True:
            report.update(completed=False, status='HOLD_THREE_FILE_FINAL_READBACK')
    return report


def save_receipt(path, report):
    finalize_report(report)
    _original_save_receipt(path, report)


def configure():
    global _configured
    if _configured:
        raise base.Hold('HOLD_INSTALLER_REENTRY')
    _configured = True
    base.ORDER = SOURCE_ORDER
    # Existing identity helper is a CAS source; preserve other runtime imports.
    base.DEPENDENCY_SHA = {
        'agent_loop.py': base.AGENT_SHA,
        'common.py': '618b2b24ffdf780e64a5d09955438dec5a9b6b8b04b3346b29c57fc750403167',
        'owner_chat_stream.py': '38f4dc2995dd2c31f1f4d6a816d485721267d7add1c789cc4693aca54233fe09',
        'nox_v29_chat_bridge.py': '9d7475428ad8c553c756ca50280ac2363e7c03854abab285de560ae066d4586a',
    }
    base.TRANSFORMS = source.TRANSFORMS
    base.transform = source.transform
    base.FileTransaction = BindingTransaction
    base.metadata_preflight = metadata_preflight
    base.service_identity = service_identity
    base.command = command
    base.save_receipt = save_receipt


def entry():
    try:
        configure()
        report = base.run(rollback=False)
    except BaseException as error:
        report = {'schema': 'NOX_CONTEXT_COUNTER_PROXY_INSTALL_V1',
                  'status': str(error) if isinstance(error, base.Hold) else 'HOLD_' + type(error).__name__.upper(),
                  'completed': False, 'installed': None, 'used': False, 'accepted': False,
                  'model_calls': 0, 'model_reloads': 0}
        if isinstance(error, base.Hold) and hasattr(error, 'lock_diagnostic'):
            report['lock_diagnostic'] = error.lock_diagnostic
    finalize_report(report)
    public = json.loads(json.dumps(report))
    for step in public.get('steps', []):
        for key in ('before', 'after'):
            if key in step and 'config' in step[key]:
                config = step[key]['config']
                values = config.pop('values')
                config['command_sha256'] = base.digest(values['command'].encode())
                config['stop_settings'] = {k: values[k] for k in ('stopasgroup', 'killasgroup', 'stopsignal', 'stopwaitsecs')}
    raw = json.dumps({'kind': 'native_context_counter_install', 'data': public}, separators=(',', ':'))
    if len(raw.encode()) > 120000:
        raw = json.dumps({'kind': 'native_context_counter_install', 'data': {
            'status': 'HOLD_PUBLIC_RECEIPT_BOUND', 'completed': False, 'manual_readback_required': True}})
        report['completed'] = False
    print('NOX_MAINT_REPAIR=' + raw, flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(report.get('completed') is True).lower(), flush=True)
    return 0 if report.get('completed') is True else 2
