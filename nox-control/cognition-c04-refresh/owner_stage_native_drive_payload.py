"""Stage one pinned native Drive helper during an authorized NOX maintenance run."""

import base64
from contextlib import ExitStack
import ctypes
import errno
import fcntl
from hashlib import sha256
import json
import os
import re
import stat
import uuid


PAYLOAD = b'IiIiVmVyaWZ5IHRoZSBOT1ggY29udGFpbmVyJ3Mgb3duIEdvb2dsZSBEcml2ZSBjb25uZWN0aW9uIGFuZCBmb2xkZXIgYmluZGluZy4iIiIKCmltcG9ydCBhcmdwYXJzZQppbXBvcnQgY29uZmlncGFyc2VyCmltcG9ydCBqc29uCmltcG9ydCBvcwpmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgKaW1wb3J0IHNlY3JldHMKaW1wb3J0IHN0YXQKaW1wb3J0IHN1YnByb2Nlc3MKaW1wb3J0IHRlbXBmaWxlCgoKQVVUSF9ESVIgPSBQYXRoKCcvcm9vdC9ub3gvc3RhdGUvZHJpdmUtYXV0aCcpCkNPTkZJRyA9IEFVVEhfRElSIC8gJ3JjbG9uZS5jb25mJwpSRUNFSVBUID0gQVVUSF9ESVIgLyAnd3JpdGUtcHJvb2YuanNvbicKRk9MREVSID0gJzFUTzB3eVpRN1BIUHlyU0J1dGlGTUhEanUyVGtfNjFrcicKUkVNT1RFID0gJ25veGNvbGQnCldFSUdIVFMgPSBSRU1PVEUgKyAnOndlaWdodHMtdjEnClJDTE9ORSA9ICcvdXNyL2Jpbi9yY2xvbmUnCk1BWF9DT05GSUdfQllURVMgPSA2NCAqIDEwMjQKCgpjbGFzcyBEcml2ZUhvbGQoUnVudGltZUVycm9yKToKICAgICIiIkEgcmVwb3J0YWJsZSBob2xkIGNvZGUgdGhhdCBjb250YWlucyBubyBjcmVkZW50aWFsIG9yIHByb3ZpZGVyIG91dHB1dC4iIiIKCgpkZWYgcmVxdWlyZShjb25kaXRpb24sIHJlYXNvbik6CiAgICBpZiBub3QgY29uZGl0aW9uOgogICAgICAgIHJhaXNlIERyaXZlSG9sZCgnSE9MRF9OQVRJVkVfRFJJVkVfJyArIHJlYXNvbikKCgpkZWYgcmVhZF9wcml2YXRlKHBhdGgsIGxpbWl0KToKICAgIGZvciBkaXJlY3RvcnkgaW4gcmV2ZXJzZWQocGF0aC5wYXJlbnRzKToKICAgICAgICBpbmZvID0gZGlyZWN0b3J5LmxzdGF0KCkKICAgICAgICByZXF1aXJlKHN0YXQuU19JU0RJUihpbmZvLnN0X21vZGUpIGFuZCBpbmZvLnN0X3VpZCA9PSBvcy5nZXRldWlkKCkKICAgICAgICAgICAgICAgIGFuZCBub3QgaW5mby5zdF9tb2RlICYgMG8wMjIsICdBVVRIX1BBVEgnKQogICAgcmVxdWlyZShub3QgcGF0aC5wYXJlbnQuc3RhdCgpLnN0X21vZGUgJiAwbzA3NywgJ0FVVEhfRElSRUNUT1JZX01PREUnKQogICAgZmxhZ3MgPSBvcy5PX1JET05MWSB8IG9zLk9fTk9GT0xMT1cgfCBvcy5PX0NMT0VYRUMgfCBvcy5PX05PTkJMT0NLCiAgICBmZCA9IG9zLm9wZW4ocGF0aCwgZmxhZ3MpCiAgICB3aXRoIG9zLmZkb3BlbihmZCwgJ3JiJykgYXMgc3RyZWFtOgogICAgICAgIGl0ZW0gPSBvcy5mc3RhdChzdHJlYW0uZmlsZW5vKCkpCiAgICAgICAgcmVxdWlyZShzdGF0LlNfSVNSRUcoaXRlbS5zdF9tb2RlKSBhbmQgaXRlbS5zdF91aWQgPT0gb3MuZ2V0ZXVpZCgpCiAgICAgICAgICAgICAgICBhbmQgaXRlbS5zdF9ubGluayA9PSAxIGFuZCBub3QgaXRlbS5zdF9tb2RlICYgMG8wNzcKICAgICAgICAgICAgICAgIGFuZCBpdGVtLnN0X3NpemUgPD0gbGltaXQsICdBVVRIX0ZJTEVfTU9ERScpCiAgICAgICAgcmF3ID0gc3RyZWFtLnJlYWQobGltaXQgKyAxKQogICAgICAgIHJlcXVpcmUoMCA8IGxlbihyYXcpIDw9IGxpbWl0LCAnQVVUSF9GSUxFX1NJWkUnKQogICAgICAgIGN1cnJlbnQgPSBwYXRoLmxzdGF0KCkKICAgICAgICByZXF1aXJlKChpdGVtLnN0X2RldiwgaXRlbS5zdF9pbm8pID09IChjdXJyZW50LnN0X2RldiwgY3VycmVudC5zdF9pbm8pLCAnQVVUSF9GSUxFX1JFUExBQ0VEJykKICAgICAgICByZXR1cm4gcmF3CgoKZGVmIGFzc2VydF9wcm9maWxlKCk6CiAgICByZXF1aXJlKG9zLmdldGV1aWQoKSA9PSAwLCAnUk9PVF9SRVFVSVJFRCcpCiAgICB0cnk6CiAgICAgICAgcGFyc2VyID0gY29uZmlncGFyc2VyLkNvbmZpZ1BhcnNlcihpbnRlcnBvbGF0aW9uPU5vbmUpCiAgICAgICAgcGFyc2VyLnJlYWRfc3RyaW5nKHJlYWRfcHJpdmF0ZShDT05GSUcsIE1BWF9DT05GSUdfQllURVMpLmRlY29kZSgndXRmLTgnKSkKICAgICAgICByZXF1aXJlKHBhcnNlci5zZWN0aW9ucygpID09IFtSRU1PVEVdIGFuZCBub3QgcGFyc2VyLmRlZmF1bHRzKCksICdSRU1PVEVfU0NPUEUnKQogICAgICAgIGNvbmZpZyA9IHBhcnNlcltSRU1PVEVdCiAgICAgICAgZXhwZWN0ZWQgPSB7J3R5cGUnOiAnZHJpdmUnLCAncm9vdF9mb2xkZXJfaWQnOiBGT0xERVIsICdzY29wZSc6ICdkcml2ZS5maWxlJ30KICAgICAgICBhbGxvd2VkID0gc2V0KGV4cGVjdGVkKSB8IHsndG9rZW4nLCAnY2xpZW50X2lkJywgJ2NsaWVudF9zZWNyZXQnfQogICAgICAgIHJlcXVpcmUoc2V0KGNvbmZpZykgPD0gYWxsb3dlZCBhbmQgYWxsKGNvbmZpZy5nZXQoaykgPT0gdiBmb3IgaywgdiBpbiBleHBlY3RlZC5pdGVtcygpKSwKICAgICAgICAgICAgICAgICdGT0xERVJfT1JfU0NPUEUnKQogICAgICAgIHRva2VuID0ganNvbi5sb2Fkcyhjb25maWcuZ2V0KCd0b2tlbicsICd7fScpKQogICAgICAgIHJlcXVpcmUoaXNpbnN0YW5jZSh0b2tlbiwgZGljdCkgYW5kIGlzaW5zdGFuY2UodG9rZW4uZ2V0KCdyZWZyZXNoX3Rva2VuJyksIHN0cikKICAgICAgICAgICAgICAgIGFuZCBib29sKHRva2VuWydyZWZyZXNoX3Rva2VuJ10pLCAnT0FVVEhfUkVRVUlSRUQnKQogICAgZXhjZXB0IChPU0Vycm9yLCBVbmljb2RlRXJyb3IsIFZhbHVlRXJyb3IsIGNvbmZpZ3BhcnNlci5FcnJvcikgYXMgZXJyb3I6CiAgICAgICAgcmFpc2UgRHJpdmVIb2xkKCdIT0xEX05BVElWRV9EUklWRV9PQVVUSF9QUk9GSUxFX1JFUVVJUkVEJykgZnJvbSBlcnJvcgoKCmRlZiBlbnZpcm9ubWVudCgpOgogICAgcmV0dXJuIHsnUEFUSCc6ICcvdXNyL2JpbjovYmluJywgJ1JDTE9ORV9DT05GSUcnOiBzdHIoQ09ORklHKSwKICAgICAgICAgICAgJ1JDTE9ORV9EUklWRV9DSFVOS19TSVpFJzogJzhNaScsICdSQ0xPTkVfQlVGRkVSX1NJWkUnOiAnMCcsICdMQ19BTEwnOiAnQyd9CgoKZGVmIHJjbG9uZSgqYXJncywgY2FwdHVyZT1GYWxzZSk6CiAgICBjb21tYW5kID0gW1JDTE9ORSwgJy0tY29uZmlnJywgc3RyKENPTkZJRyksICctLXJldHJpZXMnLCAnMScsCiAgICAgICAgICAgICAgICctLWxvdy1sZXZlbC1yZXRyaWVzJywgJzEnLCAnLS1jb250aW1lb3V0JywgJzEwcycsICphcmdzXQogICAgdHJ5OgogICAgICAgIHJlc3VsdCA9IHN1YnByb2Nlc3MucnVuKGNvbW1hbmQsIGVudj1lbnZpcm9ubWVudCgpLCB0aW1lb3V0PTQ1LAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHN0ZGluPXN1YnByb2Nlc3MuREVWTlVMTCwgc3RkZXJyPXN1YnByb2Nlc3MuREVWTlVMTCwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBzdGRvdXQ9c3VicHJvY2Vzcy5QSVBFIGlmIGNhcHR1cmUgZWxzZSBzdWJwcm9jZXNzLkRFVk5VTEwsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgY2hlY2s9RmFsc2UpCiAgICBleGNlcHQgKE9TRXJyb3IsIHN1YnByb2Nlc3MuVGltZW91dEV4cGlyZWQpIGFzIGVycm9yOgogICAgICAgIHJhaXNlIERyaXZlSG9sZCgnSE9MRF9OQVRJVkVfRFJJVkVfVFJBTlNQT1JUJykgZnJvbSBlcnJvcgogICAgcmVxdWlyZShyZXN1bHQucmV0dXJuY29kZSA9PSAwLCAnVFJBTlNQT1JUJykKICAgIHJldHVybiByZXN1bHQuc3Rkb3V0CgoKZGVmIG1hcmtlcihub25jZSk6CiAgICByZXF1aXJlKGlzaW5zdGFuY2Uobm9uY2UsIHN0cikgYW5kIGxlbihub25jZSkgPT0gMzIKICAgICAgICAgICAgYW5kIGFsbChjaGFyYWN0ZXIgaW4gJzAxMjM0NTY3ODlhYmNkZWYnIGZvciBjaGFyYWN0ZXIgaW4gbm9uY2UpLCAnUFJPT0ZfU0NIRU1BJykKICAgIGRhdGEgPSAoJ05PWF9OQVRJVkVfRFJJVkVfUFJPQkVfVjEgJyArIG5vbmNlICsgJ1xuJykuZW5jb2RlKCdhc2NpaScpCiAgICByZXR1cm4gUkVNT1RFICsgJzpuYXRpdmUtY29ubmVjdGlvbi12MS0nICsgbm9uY2UgKyAnLnR4dCcsIGRhdGEKCgpkZWYgdmVyaWZ5X3JlbW90ZV9tYXJrZXIobm9uY2UpOgogICAgcmVtb3RlLCBleHBlY3RlZCA9IG1hcmtlcihub25jZSkKICAgIG9ic2VydmVkID0gcmNsb25lKCdjYXQnLCByZW1vdGUsICctLWNvdW50Jywgc3RyKGxlbihleHBlY3RlZCkgKyAxKSwgY2FwdHVyZT1UcnVlKQogICAgcmVxdWlyZShvYnNlcnZlZCA9PSBleHBlY3RlZCwgJ1BST09GX01JU01BVENIJykKCgpkZWYgYXNzZXJ0X25hdGl2ZV9kcml2ZSgpOgogICAgYXNzZXJ0X3Byb2ZpbGUoKQogICAgdHJ5OgogICAgICAgIHByb29mID0ganNvbi5sb2FkcyhyZWFkX3ByaXZhdGUoUkVDRUlQVCwgMjA0OCkpCiAgICAgICAgcmVxdWlyZShpc2luc3RhbmNlKHByb29mLCBkaWN0KSBhbmQgc2V0KHByb29mKSA9PSB7J3NjaGVtYScsICdmb2xkZXJfaWQnLCAnbm9uY2UnfQogICAgICAgICAgICAgICAgYW5kIHByb29mWydzY2hlbWEnXSA9PSAnTk9YX05BVElWRV9EUklWRV9QUk9PRl9WMScKICAgICAgICAgICAgICAgIGFuZCBwcm9vZlsnZm9sZGVyX2lkJ10gPT0gRk9MREVSLCAnUFJPT0ZfU0NIRU1BJykKICAgIGV4Y2VwdCAoT1NFcnJvciwgVW5pY29kZUVycm9yLCBWYWx1ZUVycm9yKSBhcyBlcnJvcjoKICAgICAgICByYWlzZSBEcml2ZUhvbGQoJ0hPTERfTkFUSVZFX0RSSVZFX1dSSVRFX1BST0JFX1JFUVVJUkVEJykgZnJvbSBlcnJvcgogICAgdmVyaWZ5X3JlbW90ZV9tYXJrZXIocHJvb2ZbJ25vbmNlJ10pCiAgICByZXR1cm4gV0VJR0hUUwoKCmRlZiBwcm92ZV93cml0ZSgpOgogICAgYXNzZXJ0X3Byb2ZpbGUoKQogICAgaWYgb3MucGF0aC5sZXhpc3RzKFJFQ0VJUFQpOgogICAgICAgIHJldHVybiBhc3NlcnRfbmF0aXZlX2RyaXZlKCkKICAgIG5vbmNlID0gc2VjcmV0cy50b2tlbl9oZXgoMTYpCiAgICByZW1vdGUsIHBheWxvYWQgPSBtYXJrZXIobm9uY2UpCiAgICB3aXRoIHRlbXBmaWxlLlRlbXBvcmFyeURpcmVjdG9yeShwcmVmaXg9Jy5kcml2ZS1wcm9iZS0nLCBkaXI9QVVUSF9ESVIpIGFzIGRpcmVjdG9yeToKICAgICAgICBzb3VyY2UgPSBQYXRoKGRpcmVjdG9yeSkgLyAnbWFya2VyLnR4dCcKICAgICAgICBzb3VyY2Uud3JpdGVfYnl0ZXMocGF5bG9hZCkKICAgICAgICByY2xvbmUoJ2NvcHl0bycsIHN0cihzb3VyY2UpLCByZW1vdGUsICctLWltbXV0YWJsZScsICctLXRyYW5zZmVycycsICcxJykKICAgICAgICB2ZXJpZnlfcmVtb3RlX21hcmtlcihub25jZSkKICAgICAgICBzdGFnZWRfcHJvb2YgPSBQYXRoKGRpcmVjdG9yeSkgLyAncmVjZWlwdC5qc29uJwogICAgICAgIGZkID0gb3Mub3BlbihzdGFnZWRfcHJvb2YsIG9zLk9fV1JPTkxZIHwgb3MuT19DUkVBVCB8IG9zLk9fRVhDTCB8IG9zLk9fTk9GT0xMT1csIDBvNjAwKQogICAgICAgIHdpdGggb3MuZmRvcGVuKGZkLCAnd2InKSBhcyBzdHJlYW06CiAgICAgICAgICAgIHN0cmVhbS53cml0ZShqc29uLmR1bXBzKHsnc2NoZW1hJzogJ05PWF9OQVRJVkVfRFJJVkVfUFJPT0ZfVjEnLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgJ2ZvbGRlcl9pZCc6IEZPTERFUiwgJ25vbmNlJzogbm9uY2V9KS5lbmNvZGUoJ2FzY2lpJykpCiAgICAgICAgICAgIHN0cmVhbS5mbHVzaCgpCiAgICAgICAgICAgIG9zLmZzeW5jKHN0cmVhbS5maWxlbm8oKSkKICAgICAgICB0cnk6CiAgICAgICAgICAgIG9zLmxpbmsoc3RhZ2VkX3Byb29mLCBSRUNFSVBULCBmb2xsb3dfc3ltbGlua3M9RmFsc2UpCiAgICAgICAgZXhjZXB0IEZpbGVFeGlzdHNFcnJvcjoKICAgICAgICAgICAgcGFzcwogICAgZmQgPSBvcy5vcGVuKEFVVEhfRElSLCBvcy5PX1JET05MWSB8IG9zLk9fRElSRUNUT1JZIHwgb3MuT19OT0ZPTExPVykKICAgIHRyeToKICAgICAgICBvcy5mc3luYyhmZCkKICAgIGZpbmFsbHk6CiAgICAgICAgb3MuY2xvc2UoZmQpCiAgICByZXR1cm4gYXNzZXJ0X25hdGl2ZV9kcml2ZSgpCgoKZGVmIG1haW4oKToKICAgIHBhcnNlciA9IGFyZ3BhcnNlLkFyZ3VtZW50UGFyc2VyKGRlc2NyaXB0aW9uPV9fZG9jX18pCiAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctLXByb3ZlLXdyaXRlJywgYWN0aW9uPSdzdG9yZV90cnVlJykKICAgIGFyZ3MgPSBwYXJzZXIucGFyc2VfYXJncygpCiAgICB0cnk6CiAgICAgICAgKHByb3ZlX3dyaXRlIGlmIGFyZ3MucHJvdmVfd3JpdGUgZWxzZSBhc3NlcnRfbmF0aXZlX2RyaXZlKSgpCiAgICBleGNlcHQgKERyaXZlSG9sZCwgT1NFcnJvcikgYXMgZXJyb3I6CiAgICAgICAgcHJpbnQoZXJyb3IgaWYgaXNpbnN0YW5jZShlcnJvciwgRHJpdmVIb2xkKSBlbHNlICdIT0xEX05BVElWRV9EUklWRV9JTycpCiAgICAgICAgcmV0dXJuIDIKICAgIHByaW50KCdOT1hfTkFUSVZFX0RSSVZFPVZFUklGSUVEJykKICAgIHJldHVybiAwCgoKaWYgX19uYW1lX18gPT0gJ19fbWFpbl9fJzoKICAgIHJhaXNlIFN5c3RlbUV4aXQobWFpbigpKQo='
INSTANCE = '60509551'
NAME = 'owner_native_drive.py'
PIN = '277b5835227693d1ca37ccce03e7a8cac7b654f73ba47be5692e9cb5a8b1701d'
OPS = ('root', 'nox', 'ops')
TARGET = 'drive-auth'
LEASE = 'owner_maintenance.lock'
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class Hold(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Hold('HOLD_NATIVE_DRIVE_STAGE_' + code)


def root_directory(info):
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == info.st_gid == 0
            and not info.st_mode & 0o022, 'DIRECTORY_TRUST')


def walk(stack, names):
    fd = os.open('/', DIRECTORY)
    stack.callback(os.close, fd)
    root_directory(os.fstat(fd))
    for name in names:
        fd = os.open(name, DIRECTORY, dir_fd=fd)
        stack.callback(os.close, fd)
        root_directory(os.fstat(fd))
    return fd


def inode(info):
    return info.st_dev, info.st_ino


def named(fd, name):
    return os.stat(name, dir_fd=fd, follow_symlinks=False)


def assert_named(fd, name, info):
    entry = named(fd, name)
    require(inode(entry) == inode(info) and entry.st_mode == info.st_mode
            and entry.st_uid == entry.st_gid == 0 and entry.st_nlink == info.st_nlink,
            'PATH_CHANGED')


def readback(fd, name, raw):
    with os.fdopen(os.open(name, READ, dir_fd=fd), 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == info.st_gid == 0
                and stat.S_IMODE(info.st_mode) == 0o400 and info.st_nlink == 1
                and info.st_size == len(raw) and stream.read(len(raw) + 1) == raw,
                'FILE_READBACK')
        assert_named(fd, name, info)
    return info


def rename_no_replace(fd, old, new):
    rename = ctypes.CDLL(None, use_errno=True).renameat2
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(fd, os.fsencode(old), fd, os.fsencode(new), 1) != 0:  # RENAME_NOREPLACE
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def publish(fd, raw, assert_scope):
    try:
        readback(fd, NAME, raw)
    except FileNotFoundError:
        pass
    else:
        assert_scope()
        return False

    temporary = '.native-drive-' + uuid.uuid4().hex
    output = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o400, dir_fd=fd)
    identity = os.fstat(output)
    committed = False
    try:
        with os.fdopen(output, 'wb') as stream:
            require(stream.write(raw) == len(raw), 'WRITE')
            stream.flush()
            os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())
        require(inode(readback(fd, temporary, raw)) == inode(identity), 'STAGING_IDENTITY')
        assert_scope()
        rename_no_replace(fd, temporary, NAME)
        committed = True
        os.fsync(fd)
        require(inode(readback(fd, NAME, raw)) == inode(identity), 'FILE_IDENTITY')
        assert_scope()
        return True
    except BaseException:
        try:
            name = NAME if committed else temporary
            require(inode(named(fd, name)) == inode(identity), 'ROLLBACK_IDENTITY')
            os.unlink(name, dir_fd=fd)
            os.fsync(fd)
        except (OSError, Hold) as error:
            raise Hold('HOLD_NATIVE_DRIVE_STAGE_ROLLBACK') from error
        raise


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    owner_source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    labels = {os.environ[key].removeprefix('C.') for key in ('VAST_CONTAINERLABEL', 'CONTAINER_ID')
              if os.environ.get(key)}
    require(os.geteuid() == os.getegid() == 0 and labels == {INSTANCE}
            and re.fullmatch('[1-9][0-9]{0,19}', request)
            and re.fullmatch('[a-f0-9]{40}', owner_source), 'OWNER')
    raw = base64.b64decode(PAYLOAD, validate=True)
    require(len(raw) == 6281 and sha256(raw).hexdigest() == PIN, 'PAYLOAD_PIN')
    compile(raw, NAME, 'exec')

    with ExitStack() as stack:
        state = walk(stack, ('root', 'nox', 'state'))
        lease = os.open(LEASE, READ, dir_fd=state)
        stack.callback(os.close, lease)
        lock = os.fstat(lease)
        require(stat.S_ISREG(lock.st_mode) and lock.st_uid == lock.st_gid == 0
                and not lock.st_mode & 0o077 and lock.st_nlink == 1, 'LEASE_TRUST')
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            require(error.errno not in (errno.EAGAIN, errno.EWOULDBLOCK), 'OWNER_LEASE_BUSY')
            raise
        assert_named(state, LEASE, lock)

        ops = walk(stack, OPS)
        try:
            os.mkdir(TARGET, 0o700, dir_fd=ops)
        except FileExistsError:
            pass
        target = os.open(TARGET, DIRECTORY, dir_fd=ops)
        stack.callback(os.close, target)
        directory = os.fstat(target)
        root_directory(directory)
        require(stat.S_IMODE(directory.st_mode) == 0o700, 'TARGET_MODE')

        def assert_scope():
            assert_named(state, LEASE, lock)
            assert_named(ops, TARGET, directory)

        assert_scope()
        os.fsync(ops)
        created = publish(target, raw, assert_scope)

    receipt = {'request': request, 'source_sha': owner_source, 'sha256': PIN,
               'path': '/root/nox/ops/drive-auth/' + NAME, 'created': created}
    print('NOX_MAINT_NATIVE_DRIVE_STAGED=' + json.dumps(receipt, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (Hold, OSError, AttributeError, ValueError, SyntaxError) as error:
        code = str(error) if isinstance(error, Hold) else type(error).__name__
        print('NOX_MAINT_NATIVE_DRIVE_HOLD=' + code, flush=True)
        raise SystemExit(2) from None
