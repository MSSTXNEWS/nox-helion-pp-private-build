"""Current, read-only file evidence for the owner UI.

The immutable download manifest describes a selection.  It is never rewritten
or interpreted as transfer progress here.  Large files are not rehashed by an
HTTP poll: a native full-SHA receipt is checked against current file identity.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time

ROOT = Path('/root/nox')
MEDIA_RAM = Path('/dev/shm/nox_media')
DRIVE_RAM = Path('/dev/shm/nox_drive/3t724u')
SCHEMA = 'NOX_OWNER_DOWNLOAD_INVENTORY_V1'
INSTALLER_SHA = 'e66a5b743deb0dfaa7e1e846e11b2d06190962d9ba0ba4abb67abeca54c02ca5'
RUNTIME_SHA = 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'
DRIVE_BRIDGE_SHA = '57893b187155b12c08b3ca0612a62397d117218302d448994a346c84f556b786'
DRIVE_MANIFEST_SHA = '73b8fa9336faabad2c2b1d197d6751d79b065158c7f0700e46155f371b74c816'
SHA = re.compile(r'[a-f0-9]{64}')
MEDIA = (
    ('image', 'checkpoint', 'checkpoints', 'sdxl_lightning_4step.safetensors', 6938040682,
     'e0d996ee0013e79d9d3561f50fcafb9a17e3ff07b780358e3b66d67932c4d490'),
    ('video', 'unet', 'diffusion_models', 'wan2.1_t2v_1.3B_fp16.safetensors', 2838303560,
     'be531024cd9018cb5b48c40cfbb6a6191645b1c792eb8bf4f8c1c6e10f924dc5'),
    ('video', 'clip', 'text_encoders', 'umt5_xxl_fp8_e4m3fn_scaled.safetensors', 6735906897,
     'c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68'),
    ('video', 'vae', 'vae', 'wan_2.1_vae.safetensors', 253815318,
     '2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b'),
)
DRIVE = (
    ('core_self', 't724u_core_self_final.safetensors', 306787336,
     'e5e98c7e2969aaf2f2fdda38c5814a8764c0e607265c141096e5e673b648f476'),
    ('intellect', 't724u_intellect_best_holdout.safetensors', 306787336,
     '9e76a6bf88bff25b0b7efdf34032c72dbd7044def371be21e540319307f846b6'),
    ('builder', 't724u_builder_best_holdout.safetensors', 306787336,
     '3030a2623b279ec0586bbdf403cf7ee13a32bd0fe2bf5094538d59b7c854ddb9'),
)


class StatusUnknown(RuntimeError):
    pass


def require(condition):
    if not condition:
        raise StatusUnknown('UNVERIFIED_CURRENT_EVIDENCE')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def plain(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts)
    require(not any(item.is_symlink() for item in (path, *path.parents)))
    return path


@contextmanager
def opened(path, maximum):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and not before.st_mode & 0o022 and 0 <= before.st_size <= maximum)
        yield fd, before
        after = os.fstat(fd); current = path.stat(follow_symlinks=False)
        for name in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'):
            require(getattr(before, name) == getattr(after, name) == getattr(current, name))
    finally:
        os.close(fd)


def read(path, maximum=262144):
    with opened(path, maximum) as (fd, _):
        chunks = []; count = 0
        while True:
            part = os.read(fd, min(65536, maximum + 1 - count))
            if not part:
                return b''.join(chunks)
            count += len(part); require(count <= maximum); chunks.append(part)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result); result[key] = value
    return result


def document(path, maximum=262144):
    raw = read(path, maximum)
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(StatusUnknown()))
    require(isinstance(value, dict))
    return value, digest(raw)


def timestamp(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 < value <= time.time() + 5


def media_paths(subdir, filename):
    return (MEDIA_RAM / 'models' / subdir / filename,
            ROOT / 'media/weights/models' / subdir / filename)


def current_file(path, expected, receipt=None, device_required=True):
    """Open/stat only.  A same-size file alone is not evidence of its SHA."""
    with opened(path, expected) as (_, info):
        require(info.st_size == expected)
        if receipt is not None:
            require(receipt.get('verified') is True and receipt.get('bytes') == expected
                    and type(receipt.get('stat_inode')) is int and info.st_ino == receipt['stat_inode']
                    and type(receipt.get('stat_mtime_ns')) is int and info.st_mtime_ns == receipt['stat_mtime_ns'])
            if device_required:
                require(type(receipt.get('stat_device')) is int and info.st_dev == receipt['stat_device'])
        return info


def asset_row(kind, role, filename, size, sha, candidates, receipt=None, device_required=True):
    public = {'kind': kind, 'role': role, 'filename': filename, 'expected_bytes': size,
              'verified_bytes': 0, 'partial_bytes': 0, 'state': 'NOT_OBSERVED', 'storage': None}
    for path in candidates:
        try:
            info = current_file(path, size)
            public.update(state='PRESENT_UNVERIFIED', storage='RAM' if path.is_relative_to('/dev/shm') else 'SSD')
            if receipt is not None and receipt.get('sha256') == sha:
                current_file(path, size, receipt, device_required)
                public.update(state='SHA_VERIFIED_CURRENT_FILE', verified_bytes=info.st_size, sha256=sha)
                return public
        except (OSError, ValueError, StatusUnknown):
            pass
        try:
            with opened(path.with_name(path.name + '.partial'), size) as (_, partial):
                public['partial_bytes'] = max(public['partial_bytes'], partial.st_size)
                if public['state'] == 'NOT_OBSERVED':
                    public.update(state='PARTIAL_UNVERIFIED', storage='RAM' if path.is_relative_to('/dev/shm') else 'SSD')
        except (OSError, ValueError, StatusUnknown):
            pass
    return public


def media_evidence():
    config, config_sha = document(ROOT / 'config/owner_media_runtime.json')
    job, _ = document(ROOT / 'state/owner_media/prepare_job.json', 32768)
    request = job.get('request')
    require(isinstance(request, str) and re.fullmatch(r'[0-9]{1,24}', request))
    receipt, receipt_sha = document(ROOT / ('state/owner_media/prepare_result_' + request + '.json'), 32768)
    require(job.get('schema') == 'NOX_MEDIA_PREPARE_JOB_V1'
            and job.get('installer_sha256') == INSTALLER_SHA and job.get('runtime_sha256') == RUNTIME_SHA
            and re.fullmatch(r'[a-f0-9]{40}', job.get('source_sha', ''))
            and receipt.get('schema') == 'NOX_MEDIA_PREPARE_WORKER_V1'
            and receipt.get('request') == request and receipt.get('source_sha') == job['source_sha']
            and receipt.get('state') == 'ENGINE_AND_FILES_READY_GENERATION_ACCEPTANCE_PENDING'
            and receipt.get('config_sha256') == config_sha and timestamp(receipt.get('finished')))
    require(config.get('schema_version') == 1 and config.get('enabled') is True
            and config.get('engine_service') == 'nox-media-comfyui'
            and isinstance(config.get('assets'), list) and len(config['assets']) == len(MEDIA))
    rows = {}
    for row in config['assets']:
        require(isinstance(row, dict) and row.get('filename') not in rows)
        rows[row.get('filename')] = row
    require(set(rows) == {item[3] for item in MEDIA})
    for kind, role, subdir, filename, size, sha in MEDIA:
        row = rows[filename]
        require(row.get('kind') == kind and row.get('role') == role
                and row.get('bytes') == size and row.get('sha256') == sha
                and row.get('path') in {str(path) for path in media_paths(subdir, filename)})
    return rows, {'state': 'NATIVE_FULL_SHA_RECEIPT', 'receipt_sha256': receipt_sha,
                  'config_sha256': config_sha, 'verified_at': receipt['finished']}


def drive_evidence():
    value, receipt_sha = document(ROOT / 'state/owner_drive_ram/latest_receipt.json', 65536)
    require(value.get('schema') == 'NOX_DRIVE_RAM_RECEIPT_V1'
            and value.get('state') == 'RAM_FILES_SHA_VERIFIED_NOT_MERGED'
            and value.get('manifest_sha256') == DRIVE_MANIFEST_SHA
            and value.get('weights_merged') is False and value.get('active_model_changed') is False
            and value.get('private_urls_exported') is False and value.get('ram_is_durable_backup') is False
            and timestamp(value.get('finished_at')) and isinstance(value.get('assets'), list)
            and len(value['assets']) == 3 and SHA.fullmatch(value.get('envelope_sha256', ''))
            and re.fullmatch(r'[0-9]{1,24}', value.get('request', ''))
            and re.fullmatch(r'[a-f0-9]{40}', value.get('source_sha', '')))
    consumed, _ = document(ROOT / ('state/owner_drive_ram/consumed/' + value['envelope_sha256'] + '.json'), 65536)
    require(consumed == value and digest(read(ROOT / 'scripts/owner_drive_ram_bridge.py')) == DRIVE_BRIDGE_SHA)
    rows = {}
    for row in value['assets']:
        require(isinstance(row, dict) and row.get('filename') not in rows)
        rows[row.get('filename')] = row
    require(set(rows) == {item[1] for item in DRIVE})
    for role, filename, size, sha in DRIVE:
        row = rows[filename]
        require(row.get('role') == role and row.get('bytes') == size and row.get('sha256') == sha)
    return rows, {'state': 'NATIVE_JOINED_FULL_SHA_RECEIPT', 'receipt_sha256': receipt_sha,
                  'verified_at': value['finished_at'], 'restore_performed_merge': False}


def generation_evidence():
    """Historical synthetic decode/delivery proof, never private job prompts."""
    result = {kind: {'state': 'NOT_VERIFIED', 'verified': False} for kind in ('image', 'video')}
    directory = ROOT / 'state/owner_media_acceptance'
    try:
        plain(directory)
        names = []
        with os.scandir(directory) as entries:
            for index, entry in enumerate(entries):
                require(index < 100)
                if re.fullmatch(r'accepted_[0-9]{1,24}\.json', entry.name):
                    names.append(entry.name)
        for name in sorted(names, key=lambda item: int(item[9:-5]), reverse=True)[:8]:
            try:
                value, sha = document(directory / name)
                require(value.get('schema') == 'NOX_OWNER_MEDIA_ACCEPTANCE_V1'
                        and value.get('state') == 'GENERATED_DECODED_AND_GPU_RELEASED'
                        and value.get('generation_verified') is True and timestamp(value.get('finished_at'))
                        and value.get('private_text_exported') is False and value.get('pixels_exported') is False
                        and isinstance(value.get('source_pins'), dict)
                        and value['source_pins'].get('runtime_sha256') == RUNTIME_SHA
                        and isinstance(value.get('artifacts'), list) and len(value['artifacts']) == 2)
                artifacts = {item.get('kind'): item for item in value['artifacts'] if isinstance(item, dict)}
                require(set(artifacts) == {'image', 'video'})
                for kind, item in artifacts.items():
                    decode = item.get('decode') or {}
                    require(item.get('decode_verified') is True and item.get('authenticated_http_verified') is True
                            and isinstance(decode, dict) and type(decode.get('frames')) is int
                            and decode['frames'] >= (2 if kind == 'video' else 1)
                            and SHA.fullmatch(item.get('sha256', '')))
                return {kind: {'state': 'SYNTHETIC_GENERATION_DECODE_AND_DELIVERY_VERIFIED',
                               'verified': True, 'verified_at': value['finished_at'], 'receipt_sha256': sha}
                        for kind in result}
            except (OSError, ValueError, TypeError, StatusUnknown):
                continue
    except (OSError, ValueError, TypeError, StatusUnknown):
        pass
    return result


def group(rows, proof):
    verified = [row for row in rows if row['state'] == 'SHA_VERIFIED_CURRENT_FILE']
    return {'state': 'ALL_FILES_VERIFIED' if len(verified) == len(rows) else 'CURRENT_EVIDENCE_INCOMPLETE',
            'selected_files': len(rows), 'verified_files': len(verified),
            'selected_bytes': sum(row['expected_bytes'] for row in rows),
            'verified_bytes': sum(row['verified_bytes'] for row in rows),
            'partial_bytes_unverified': sum(row['partial_bytes'] for row in rows),
            'assets': rows, 'proof': proof}


def snapshot():
    started = time.time()
    media = {}; drive = {}
    media_proof = drive_proof = {'state': 'RECEIPT_UNAVAILABLE_OR_CHANGED'}
    try:
        media, media_proof = media_evidence()
    except (OSError, ValueError, TypeError, StatusUnknown):
        pass
    try:
        drive, drive_proof = drive_evidence()
    except (OSError, ValueError, TypeError, StatusUnknown):
        pass
    media_rows = []
    for kind, role, subdir, filename, size, sha in MEDIA:
        row = media.get(filename)
        paths = (Path(row['path']),) if row else media_paths(subdir, filename)
        media_rows.append(asset_row(kind, role, filename, size, sha, paths, row))
    drive_rows = [asset_row('adapter', role, filename, size, sha, (DRIVE_RAM / filename,),
                            drive.get(filename), device_required=False)
                  for role, filename, size, sha in DRIVE]
    media_status = group(media_rows, media_proof)
    media_status['generation_acceptance'] = generation_evidence()
    media_status['live_engine_status_endpoint'] = '/api/ui/media'
    drive_status = group(drive_rows, drive_proof)
    drive_status.update(storage='VOLATILE_RAM', durable_backup_proven=False,
                        current_model_merge_inclusion='NOT_VERIFIED', automatic_merge=False)
    try:
        selection_sha = digest(read(ROOT / 'config/owner_download_manifest.json'))
    except (OSError, ValueError, TypeError, StatusUnknown):
        selection_sha = None
    return {'schema': SCHEMA, 'observed_at': started, 'completed_at': time.time(), 'read_only': True,
            'scope': 'NATIVE_SHA_RECEIPTS_AND_CURRENT_FILE_IDENTITIES',
            'large_file_hashes_recomputed': False, 'private_content_exported': False,
            'selection_manifest': {'sha256': selection_sha, 'is_transfer_status': False},
            'media': media_status, 'drive_adapters': drive_status}
