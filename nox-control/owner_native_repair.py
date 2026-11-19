"""Install the version-pinned V38 modules beside the existing NOX chat."""

import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile


BUNDLE = __NOX_BUNDLE_JSON__
PINS = {"brain_init.py":"01178973745df411a15bd452f925b9c5234d2566b5e4a1ab0a2fcc586d3a1a22","synaptic_brain.py":"5f5c5778c4c92bdc9c81e5d434d5df5434b4a29dfceaf52fb8584a8a60595732","native_bridge_v38.py":"270dc33a33e8323f9762106db1547139af738d5f26c89e48daeecb565be8d463","durable_runtime.py":"83a34c33aad6f0597b2ef2825427fc3b539da576b19c2169aef9408b6916bea7"}
OPS = Path('/root/nox/ops')
TARGET = OPS / 'nox-brain-v38'
LOCK = Path('/root/nox/state/owner_maintenance.lock')
PATHS = {
    'brain_init.py': 'v38/__init__.py',
    'synaptic_brain.py': 'v38/synaptic_brain.py',
    'native_bridge_v38.py': 'v38/native_bridge_v38.py',
    'durable_runtime.py': 'v38/durable_runtime.py',
}


def require(condition, code):
    if not condition:
        raise RuntimeError('HOLD_COGNITION_INSTALL_' + code)


def trusted(path):
    for part in (path, *path.parents):
        info = part.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0
                and not info.st_mode & 0o022, 'DIRECTORY')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def contents():
    require(set(BUNDLE) == set(PINS) == set(PATHS), 'ASSET_SET')
    data = {}
    for name, destination in PATHS.items():
        raw = base64.b64decode(BUNDLE[name], validate=True)
        require(len(raw) <= 256 * 1024 and digest(raw) == PINS[name], 'ASSET_SHA')
        compile(raw, destination, 'exec')
        data[destination] = raw
    data['release.json'] = (json.dumps({'schema': 'NOX_V38_STAGE_V1', 'files_sha256': {
        path: digest(raw) for path, raw in data.items()}}, sort_keys=True) + '\n').encode()
    return data


def readback(root, data):
    trusted(root / 'v38')
    for relative, raw in data.items():
        path = root / relative
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
                    and not info.st_mode & 0o022 and info.st_nlink == 1
                    and stream.read(len(raw) + 1) == raw, 'READBACK')


def stage(source):
    if os.path.lexists(TARGET):
        readback(TARGET, source)
        return False
    with tempfile.TemporaryDirectory(prefix='.nox-v38-stage-', dir=OPS) as temporary:
        release = Path(temporary) / 'release'
        release.mkdir(mode=0o755)
        (release / 'v38').mkdir(mode=0o755)
        for relative, raw in source.items():
            fd = os.open(release / relative, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644)
            with os.fdopen(fd, 'wb') as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
        sync_dir(release / 'v38')
        sync_dir(release)
        readback(release, source)
        require(not os.path.lexists(TARGET), 'TARGET_APPEARED')
        os.rename(release, TARGET)
        sync_dir(OPS)
    readback(TARGET, source)
    return True


def main():
    labels = {os.environ[key].removeprefix('C.') for key in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
              if os.environ.get(key)}
    require(os.geteuid() == os.getegid() == 0 and labels == {'60509551'}
            and re.fullmatch('[1-9][0-9]{0,19}', os.environ.get('NOX_OWNER_REQUEST_ID', ''))
            and re.fullmatch('[a-f0-9]{40}', os.environ.get('NOX_OWNER_SOURCE_SHA', '')), 'OWNER')
    trusted(OPS)
    trusted(LOCK.parent)
    fd = os.open(LOCK, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
                and not info.st_mode & 0o077 and info.st_nlink == 1, 'LEASE')
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        current = LOCK.lstat()
        require((info.st_dev, info.st_ino) == (current.st_dev, current.st_ino), 'LEASE_CHANGED')
        source = contents()
        created = stage(source)
    finally:
        os.close(fd)
    result = {'created': created, 'module_count': len(PATHS), 'release_dir': str(TARGET),
              'manifest_sha256': digest(source['release.json']), 'live_route_activated': False}
    print('NOX_MAINT_COGNITION_INSTALLED=' + json.dumps(result, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        value = str(error)
        print('NOX_MAINT_COGNITION_HOLD=' + (value if re.fullmatch('HOLD_[A-Z0-9_]+', value)
                                               else type(error).__name__), flush=True)
        raise SystemExit(2) from None
