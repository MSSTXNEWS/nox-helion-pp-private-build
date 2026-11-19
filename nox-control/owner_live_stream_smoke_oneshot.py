#!/usr/bin/env python3
"""Read-only provider presence with an authenticated local Supervisor peer."""
import http.client
import base64
import json
import tempfile
import os
from pathlib import Path
import socket
import stat
import struct
from xml.parsers.expat import ExpatError
import xmlrpc.client


KEYS = {'openrouter': b'OPENROUTER_API_KEY', 'groq': b'GROQ_API_KEY',
        'gemini': b'GEMINI_API_KEY'}
SOCKET = Path('/run/supervisor.sock')
EXPECTED = {
    'nox-proxy': (850982, 190571793, (b'/root/nox/scripts/chat_proxy.py',)),
    'nox-dispatcher-t855u': (762906, None, (
        b'/root/nox/scripts/owner_subagent_dispatcher.py',
    )),
}


def present(raw):
    return isinstance(raw, bytes) and bool(raw.strip()) and b'\r' not in raw and b'\n' not in raw


def project_environment(data):
    result = dict.fromkeys(KEYS, False)
    names = {name: provider for provider, name in KEYS.items()}
    for entry in data.split(b'\0'):
        name, separator, value = entry.partition(b'=')
        if separator and name in names:
            key = names[name]
            result[key] = result[key] or present(value)
    return result


def read_proc(pid, name, limit):
    path = Path('/proc') / str(pid) / name
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError('PROC_FIELD_SIZE')
    return data


def process_identity(pid):
    fields = read_proc(pid, 'stat', 4096).rpartition(b') ')[2].split()
    if len(fields) < 20 or fields[0] in (b'Z', b'X'):
        raise ValueError('PROCESS_NOT_LIVE')
    return int(fields[19]), int(fields[1]), int(fields[2])


def supervisor_process(pid):
    args = read_proc(pid, 'cmdline', 16384).split(b'\0')
    return any(arg.rsplit(b'/', 1)[-1] == b'supervisord' for arg in args[:2])


def socket_identity():
    directory = SOCKET.parent.lstat()
    endpoint = SOCKET.lstat()
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid or directory.st_mode & 0o022
            or not stat.S_ISSOCK(endpoint.st_mode) or endpoint.st_uid or endpoint.st_gid
            or endpoint.st_nlink != 1 or stat.S_IMODE(endpoint.st_mode) != 0o700):
        raise ValueError('UNVERIFIED_SUPERVISOR_SOCKET')
    return endpoint.st_dev, endpoint.st_ino


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self):
        super().__init__('localhost', timeout=2)
        self.peer = None

    def connect(self):
        channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            channel.settimeout(self.timeout)
            channel.connect(str(SOCKET))
            pid, uid, gid = struct.unpack('3i', channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != 0 or gid != 0 or pid <= 1 or not supervisor_process(pid):
                raise ValueError('UNVERIFIED_SUPERVISOR_PEER')
            self.peer = pid
            self.sock = channel
        except BaseException:
            channel.close()
            raise


def supervisor_read(name):
    if name not in EXPECTED:
        raise ValueError('SUPERVISOR_SERVICE_SCOPE')
    generation = socket_identity()
    http = UnixHTTP()
    try:
        raw = xmlrpc.client.dumps((name,), methodname='supervisor.getProcessInfo')
        http.request('POST', '/RPC2', raw, {'Content-Type': 'text/xml', 'Connection': 'close'})
        response = http.getresponse()
        body = response.read(65537)
        if response.status != 200 or not 0 < len(body) <= 65536 or socket_identity() != generation:
            raise ValueError('SUPERVISOR_RESPONSE_SCOPE')
        values, _ = xmlrpc.client.loads(body)
        if len(values) != 1 or not isinstance(values[0], dict):
            raise ValueError('SUPERVISOR_RESPONSE_FORMAT')
        item = values[0]
        pid = item.get('pid')
        if (item.get('name') != name or item.get('group') != name or item.get('statename') != 'RUNNING'
                or type(pid) is not int or pid <= 1):
            raise ValueError('SUPERVISOR_SERVICE_NOT_RUNNING')
        return pid, http.peer
    finally:
        http.close()


PROBE_ERRORS = (OSError, ValueError, IndexError, http.client.HTTPException,
                xmlrpc.client.Error, ExpatError)


def service_projection(name):
    report = {'program': name, 'state': 'UNOBSERVED', 'keys_present': dict.fromkeys(KEYS, None)}
    signature = None
    try:
        pid, supervisor_pid = supervisor_read(name)
        basis = 'SUPERVISOR_RPC_PEER_PROCESS_MATCH'
    except PROBE_ERRORS:
        pid, start, paths = EXPECTED[name]
        try:
            signature = process_identity(pid)
            supervisor_pid = signature[1]
            args = read_proc(pid, 'cmdline', 16384).split(b'\0')
            if (start is not None and signature[0] != start or not supervisor_process(supervisor_pid)
                    or not any(args.count(path) == 1 for path in paths)):
                return report
        except PROBE_ERRORS:
            return report
        basis = 'PINNED_PROCESS_EXECUTABLE_MATCH'
    try:
        before = process_identity(pid)
        if before[1:] != (supervisor_pid, pid) or signature is not None and before != signature:
            return report
        keys = project_environment(read_proc(pid, 'environ', 131072))
        if (before != process_identity(pid) or signature is None
                and supervisor_read(name) != (pid, supervisor_pid)):
            return dict(report, state='PROCESS_REPLACED_DURING_READ')
    except PROBE_ERRORS:
        return dict(report, state='ENV_READ_UNAVAILABLE')
    return dict(report, state='EXEC_ENV_PRESENCE_ONLY', binding=basis, keys_present=keys)


def main():
    row = {'schema': 'NOX_ADVISOR_PROVIDER_READINESS_V2',
           'probe_keys_present': {provider: present(os.environb.get(key)) for provider, key in KEYS.items()},
           'services': [service_projection(name) for name in EXPECTED],
           'configured_bundle_secret_file_names': False,
           'key_values_reported': False, 'provider_contacted': False,
           'account_or_quota_verified': False}
    with tempfile.TemporaryDirectory(prefix='nox-readiness-') as directory:
        certificate = Path(directory) / 'recipient.pem'
        certificate.write_text("-----BEGIN CERTIFICATE-----\nMIIDHTCCAgWgAwIBAgIUGhvCI9bLCW2erfpiXFSvd26u3p8wDQYJKoZIhvcNAQEL\nBQAwHjEcMBoGA1UEAwwTTk9YLVJlbGF5LVJlYWRpbmVzczAeFw0yNjExMTkxODI1\nNTJaFw0yNjExMjAxODI1NTJaMB4xHDAaBgNVBAMME05PWC1SZWxheS1SZWFkaW5l\nc3MwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDFAv06JCVvm9qsImKD\nOQ8ODHNev9FF0UKrDXvsYxPVoxyIPdAbDtQPnxlZyGA7yUM8jtEHs4UDyOLLc+Se\nr3rIP1a4oDXneqFwNe7NBZ+1AwJiuKWOXPfzziD79f1wlLBuVwvVeHi2sS65+d19\nPxOap+PKOI0A7zSr5WWCMwuRGjeinOvsZU3m7fKe57g7OkhdxCWaSE32Jrb6jJKL\n7zPsZpM89edsOyatBFnJR/mE5TQBljuq3iVez5sTkDzAvRJh7vgSB+Bp3ZPHd/Fv\ntkeMoG/YjNWyNKr2ZHC431p3kl8ApYXHFix/TuvLM+QYIWBouXyhhh3XEi4K7+U/\nk5WHAgMBAAGjUzBRMB0GA1UdDgQWBBSC70OSZC8ehG5PVo5CBLbk1Qj57TAfBgNV\nHSMEGDAWgBSC70OSZC8ehG5PVo5CBLbk1Qj57TAPBgNVHRMBAf8EBTADAQH/MA0G\nCSqGSIb3DQEBCwUAA4IBAQAf8luGRWoLNVDTV1L804cWssLOEl1nEZJTbjLR5OdZ\nAAsy38FTG9ziZfj0KYoA1H9LecZrkHjZgOTKrmKAfGbsKbib37vm4K465YGC20ws\n72GEWNpHFqdldoWy3H7vdZC5ab4JqhOenN3Wl6Pkbhgr1k5YqGqC6CCvRZQReBtO\n4jY59RN/ppMSiU0feOsvRGlcLzFai3jg9qNxAEvey03xXPdFh4zFCsTYsGjl3hqI\nW+fJs9jZIRcnpO7QuuyorKc4PzkXO47QJenqN4Cvfc4J+NjcZaSdNVOTVbPGuRa1\n09G5FC1UogVvTYqHk8noRzIEcdx45e1/158d9qEQYbx/\n-----END CERTIFICATE-----\n", encoding='ascii')
        envelope = subprocess.run(
            ['/usr/bin/openssl', 'cms', '-encrypt', '-binary', '-aes-256-cbc', '-outform', 'DER', str(certificate)],
            input=json.dumps(row, separators=(',', ':')).encode('utf-8'),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=6,
        ).stdout
    print('NOX_MAINT_SCOPE_ADVISOR_ENCRYPTED=' + base64.b64encode(envelope).decode('ascii'), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    main()
