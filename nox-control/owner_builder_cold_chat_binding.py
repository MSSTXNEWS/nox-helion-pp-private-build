"""One runtime status overlay; frozen inventory/evidence sources stay exact."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import sys

LOCATION_SHA = 'f573a7c5509786139b80768bc009fcbbae89c1a088e3d81361aa0d9eb7dbd965'
STATUS_SHA = '574bd91bb072a626b32fc557299e245b61a8798204fffd690099ffd78fc09eda'
EVIDENCE_SHA = 'ea66e05f30472b066444058ac18d0c7af74def410bde760396d1e2431161e8b2'


def evidence_module():
    name = 'owner_chat_evidence'; path = Path('/root/nox/scripts') / (name + '.py')
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise RuntimeError('HOLD_BUILDER_COLD_EVIDENCE_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd); raw = os.pread(fd, 262145, 0)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_mode & 0o022
                or len(raw) != before.st_size or len(raw) > 262144
                or hashlib.sha256(raw).hexdigest() != EVIDENCE_SHA
                or any(getattr(before, k) != getattr(os.fstat(fd), k)
                       or getattr(before, k) != getattr(path.lstat(), k) for k in fields)):
            raise RuntimeError('HOLD_BUILDER_COLD_EVIDENCE_PIN')
    finally:
        os.close(fd)
    existing = sys.modules.get(name)
    if existing is not None:
        if getattr(existing, '__file__', None) != str(path):
            raise RuntimeError('HOLD_BUILDER_COLD_EVIDENCE_ORIGIN')
        return existing
    value = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    sys.modules[name] = value
    return value


def overlay_snapshot(value, status, location):
    # Failure remains incomplete evidence, never an automatic generic symlink
    # exception or a claim that the former RAM file is still resident.
    group = value['drive_adapters']
    rows = [dict(row) for row in group['assets']]
    proof = dict(group['proof'])
    try:
        cold = location.locate()
        matches = [i for i, row in enumerate(rows) if row.get('role') == 'builder' and row.get('filename') == location.ALIAS.name]
        if len(matches) != 1:
            raise RuntimeError('HOLD_BUILDER_COLD_STATUS_ROW')
        rows[matches[0]] = location.public_row(cold)
        proof['builder_storage_transition_sha256'] = cold['receipt_sha256']
        proof['old_ram_receipt_is_historical'] = True
    except (OSError, ValueError, TypeError, RuntimeError):
        proof['builder_storage_transition'] = 'UNVERIFIED_OR_NOT_PRESENT'
    result = status.group(rows, proof)
    counts = {'RAM': sum(r['state'] == 'SHA_VERIFIED_CURRENT_FILE' and r.get('storage') == 'RAM' for r in rows),
              'SSD': sum(r['state'] == 'SHA_VERIFIED_CURRENT_FILE' and r.get('storage') == 'SSD' for r in rows)}
    result.update(storage='MIXED_RAM_AND_COLD_SSD' if counts['SSD'] else 'VOLATILE_RAM',
                  storage_counts=counts, durable_backup_proven=False,
                  current_model_merge_inclusion='NOT_VERIFIED', automatic_merge=False)
    return {**value, 'drive_adapters': result}


def bind():
    evidence = evidence_module()
    if getattr(evidence, '_owner_builder_cold_bound', False):
        return
    path = evidence.ROOT / 'scripts/owner_chat_evidence.py'
    evidence.require(hashlib.sha256(evidence._read(path)).hexdigest() == EVIDENCE_SHA, 'HOLD_BUILDER_COLD_EVIDENCE_PIN')
    status = evidence._module('owner_download_status')
    evidence.require(hashlib.sha256(evidence._read(Path(status.__file__))).hexdigest() == STATUS_SHA, 'HOLD_BUILDER_COLD_STATUS_PIN')
    path = evidence.ROOT / 'scripts/owner_builder_cold_location.py'; raw = evidence._read(path)
    evidence.require(hashlib.sha256(raw).hexdigest() == LOCATION_SHA, 'HOLD_BUILDER_COLD_LOCATION_PIN')
    location = importlib.util.module_from_spec(importlib.util.spec_from_loader('_nox_builder_cold_location', loader=None))
    location.__file__ = str(path); exec(compile(raw, str(path), 'exec'), location.__dict__)
    old_snapshot, old_project = status.snapshot, evidence.project

    def snapshot():
        return overlay_snapshot(old_snapshot(), status, location)

    def project(value):
        result = old_project(value)
        result['drive_adapters']['storage_counts'] = dict(value['drive_adapters'].get('storage_counts', {}))
        result['drive_adapters']['builder_location_state'] = next((r.get('location_state', 'UNVERIFIED')
            for r in value['drive_adapters']['assets'] if r.get('role') == 'builder'), 'UNVERIFIED')
        return result

    def inventory_reply():
        value = evidence.current_evidence()
        if value.get('state') != 'CURRENT_FILE_IDENTITIES_CHECKED':
            return 'Не могу сейчас подтвердить состояние выбранных загрузок: действующая квитанция или текущая проверка файлов недоступна.'
        media, drive = value['media'], value['drive_adapters']; counts = drive.get('storage_counts', {})
        line = (f"Подтверждены {media['verified_files']}/4 файла SDXL-Lightning и Wan2.1 "
                f"({media['verified_bytes']:,} байт) и {drive['verified_files']}/3 адаптера 3t724u "
                f"({drive['verified_bytes']:,} байт): {counts.get('RAM', 0)} в RAM, {counts.get('SSD', 0)} на SSD.")
        if drive.get('builder_location_state') == 'COLD_ON_SSD':
            line += '\nBuilder хранится как холодная SSD-копия. Ссылка из каталога RAM не означает загрузку весов в RAM; автоматическая повторная подгрузка отключена для этого файла.'
        tests = media['generation_test_verified']
        line += '\nПробная генерация: фото — ' + ('подтверждена' if tests['image'] else 'не подтверждена')
        line += ', видео — ' + ('подтверждена' if tests['video'] else 'не подтверждена') + '.'
        return line + '\nДанные основаны на полных SHA256 и текущих идентификаторах файлов. Включение адаптеров в чат-веса не подтверждено; RAM не является долговременным резервом.'

    status.snapshot = snapshot; evidence.project = project; evidence.inventory_reply = inventory_reply
    evidence._owner_builder_cold_bound = True
