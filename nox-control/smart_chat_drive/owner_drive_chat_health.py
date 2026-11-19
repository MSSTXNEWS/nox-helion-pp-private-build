"""Owner chat status backed by the existing noxdrive read probe."""

import asyncio
from datetime import datetime, timezone
import time


SCHEMA = 'NOX_WEB_DRIVE_HEALTH_V1'
PROBE_SCHEMA = 'NOX_DRIVE_AUTH_OWNER_PROBE_V1'
INSTANCE = 60509551
APPROVED_ROOT = '1ewQ-R7z33fN0fKoMNNuFzv1_3rCEP96v'
CHECK_TIMEOUT = 27

PROFILE_ERRORS = {
    'CONFIG_PERMISSIONS', 'CONFIG_SIZE', 'CONFIG_UNREADABLE',
    'BACKEND_NOT_DRIVE', 'ROOT_NOT_PINNED', 'CREDENTIALS_NOT_CONFIGURED',
}
READ_ERRORS = {'RCLONE_MISSING', 'LIST_TIMEOUT', 'LIST_ERROR', 'READ_UNAVAILABLE'}


def _status(state, *, profile='UNKNOWN', root='UNVERIFIED', read_access='UNVERIFIED',
            reason, message, checked_at=None):
    return {'schema': SCHEMA, 'state': state, 'profile': profile, 'root': root,
            'read_access': read_access, 'write_access': 'NOT_TESTED', 'reason': reason,
            'message': message, 'checked_at': checked_at}


def _unknown(reason, checked_at=None):
    return _status('UNKNOWN', reason=reason, checked_at=checked_at,
                   message='NOX пока не подтвердил доступ к Google Drive.')


def project_drive_health(row, checked_at):
    """Emit a fixed allowlist of fields. Never return native paths or probe output."""
    if (type(row) is not dict or row.get('schema') != PROBE_SCHEMA or row.get('instance_id') != INSTANCE
            or row.get('approved_root_id') != APPROVED_ROOT or row.get('write_access') != 'NOT_TESTED'
            or type(row.get('root_pinned')) is not bool or type(row.get('read_access')) is not bool
            or type(row.get('state')) is not str or type(row.get('config_state')) is not str):
        return _unknown('PROBE_RESULT_UNVERIFIED', checked_at)
    state, config = row['state'], row['config_state']
    root = 'PINNED' if row['root_pinned'] else 'UNVERIFIED'
    if state == 'READ_CONNECTED' and config == 'CONFIG_OK' and row['root_pinned'] and row['read_access']:
        return _status('CONNECTED', profile='READY', root='VERIFIED_READ', read_access='VERIFIED',
                       reason='ROOT_READ_VERIFIED', checked_at=checked_at,
                       message='NOX прочитал корень Google Drive. Запись не проверялась.')
    if row['read_access']:
        return _unknown('PROBE_RESULT_UNVERIFIED', checked_at)
    if state == 'NOT_CONNECTED' and config in {'CONFIG_MISSING', 'REMOTE_MISSING'} and not row['root_pinned']:
        return _status('NOT_CONNECTED', profile='MISSING', reason=config, checked_at=checked_at,
                       message='На сервере NOX отсутствует профиль Google Drive.')
    if (state == 'NOT_CONNECTED' and config in PROFILE_ERRORS) or (config == 'CONFIG_OK' and state in PROFILE_ERRORS):
        return _status('NOT_CONNECTED', profile='INVALID', root=root, checked_at=checked_at,
                       reason=config if state == 'NOT_CONNECTED' else state,
                       message='Настройки или разрешения профиля Google Drive не прошли проверку.')
    if config == 'CONFIG_OK' and row['root_pinned'] and state in READ_ERRORS:
        return _status('NOT_CONNECTED', profile='CONFIGURED', root=root, read_access='UNAVAILABLE',
                       reason=state, checked_at=checked_at,
                       message='Настройки профиля Google Drive найдены. Чтение корня не подтверждено.')
    return _unknown('PROBE_RESULT_UNVERIFIED', checked_at)


class DriveHealth:
    """Reuse bounded native read probes across chat and WEB on the same ASGI loop."""

    def __init__(self, probe):
        if not callable(probe):
            raise ValueError('NATIVE_DRIVE_PROBE_REQUIRED')
        self._probe = probe
        self._result = None
        self._checked = 0.0
        self._started = 0.0
        self._task = None

    async def _refresh(self):
        try:
            row = await asyncio.to_thread(self._probe)
        except Exception:
            row = None
        checked_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
        self._result = project_drive_health(row, checked_at)
        self._checked = time.monotonic()
        return self._result

    async def status(self, *, wait_for_result=False):
        now = time.monotonic()
        if self._result is not None and now - self._checked < 15:
            return dict(self._result)
        if self._task is None or self._task.done():
            self._started = now
            self._task = asyncio.create_task(self._refresh())
        remaining = CHECK_TIMEOUT - (now - self._started)
        if remaining <= 0:
            return _unknown('PROBE_DEADLINE_EXCEEDED')
        budget = remaining if wait_for_result else min(0.35, remaining)
        try:
            return dict(await asyncio.wait_for(asyncio.shield(self._task), timeout=budget))
        except asyncio.TimeoutError:
            if wait_for_result or time.monotonic() - self._started >= CHECK_TIMEOUT:
                return _unknown('PROBE_DEADLINE_EXCEEDED')
            return _status('CHECKING', reason='PROBE_IN_PROGRESS',
                           message='NOX проверяет чтение Google Drive.')
