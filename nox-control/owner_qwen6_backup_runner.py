#!/usr/bin/env python3
"""Explicit owner workflow transport: exact native export to ciphertext artifacts.

Only the pinned authentication prefix of owner_native_operator is reused; its
native payload dispatcher/main are never called. No plaintext is written here.
"""
from __future__ import annotations
import argparse
import ast
import base64
import contextlib
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import socket
import struct
import subprocess
import sys
import time

import owner_qwen6_backup_stream as core

REPO = 'MSSTXNEWS/nox-helion-pp-private-build'
OWNER_ID = 340718567
WORKFLOW = '.github/workflows/nox-v61-encrypted-checkpoint-export.yml'
REPOSITORY = Path(__file__).resolve().parents[1]
AUTH_PREFIX_SHA = '095508ea245b95ac9d1623c5919de551a5c67ec47e2f561a4b3eafad800d6728'
SSH_HELPER_SHA = 'f7d0492155133ae0d5606cf663df1bd55a8a31f9966f632dd5f781d5fc429f0e'
HOST_PIN = 'SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc'
CORE_SHA = 'e9a78cd60c5cada7d9f3df5ce82c872bd11b805e8d31aee4707983a94d01c353'
PUBLIC_SHA = 'd96382c13bd039dcd85551c36b68bebde4e5b7d93d4a711b30ce75c05d93dc32'
PUBLIC_PEM_SHA = 'da4df5341302cdb5e804161c11a9c4c91e796c7d833b2fc7c0891d261a5888aa'
OUTPUT = REPOSITORY / 'artifacts/qwen6-checkpoint-backup'


def authorize_event():
    e = core.document(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes(), 2 * 1024 ** 2)
    inputs = e.get('inputs') or {}
    source = os.environ.get('NOX_PINNED_SOURCE_SHA', '')
    core.require(os.environ.get('GITHUB_REPOSITORY') == REPO
                 and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
                 and os.environ.get('GITHUB_ACTOR') == 'MSSTXNEWS'
                 and os.environ.get('GITHUB_ACTOR_ID') == str(OWNER_ID)
                 and e.get('sender', {}).get('id') == OWNER_ID
                 and e.get('repository', {}).get('owner', {}).get('id') == OWNER_ID
                 and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'EXPLICIT_OWNER_EVENT')
    core.require(inputs.get('allow_native') == 'YES' and inputs.get('checkpoint_scope') == 'QWEN6'
                 and isinstance(source, str) and re.fullmatch('[a-f0-9]{40}', source)
                 and inputs.get('source_sha') == source and os.environ.get('GITHUB_SHA') == source
                 and os.environ.get('GITHUB_WORKFLOW_REF', '').startswith(REPO + '/' + WORKFLOW + '@'), 'EXACT_WORKFLOW_SCOPE')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPOSITORY, text=True, timeout=5).strip()
    core.require(head == source, 'CHECKOUT_SHA')
    run_id = os.environ.get('GITHUB_RUN_ID', '')
    core.require(re.fullmatch('[0-9]{1,24}', run_id) is not None, 'RUN_ID')
    return source, run_id


def authentication_namespace():
    path = REPOSITORY / 'nox-control/owner_native_operator.py'
    source = path.read_text()
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_native']
    core.require(len(functions) == 1, 'AUTH_FUNCTION')
    fn = functions[0]
    anchors = [n for n in fn.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'payload' for t in n.targets)]
    core.require(len(anchors) == 1, 'AUTH_PREFIX_ANCHOR')
    prefix = ''.join(source.splitlines(keepends=True)[fn.lineno - 1:anchors[0].lineno - 1])
    core.require(core.digest(prefix.encode()) == AUTH_PREFIX_SHA, 'AUTH_PREFIX_PIN')
    helper = REPOSITORY / 'nox_runpod/teacher_mesh/v51/ephemeral_ssh_probe.py'
    core.require(core.digest(helper.read_bytes()) == SSH_HELPER_SHA, 'SSH_HELPER_PIN')
    ns = {'__file__': str(path), 'sys': sys, 'Path': Path, 'os': os, 're': re, 'ipaddress': ipaddress,
          'socket': socket, 'subprocess': subprocess, 'json': json, 'time': time,
          'INSTANCE': core.INSTANCE, 'PIN': HOST_PIN, 'MASTER': None}
    # Exact prefix ends before payload selection. Only this added return is new.
    exec(compile(prefix + '    return common, host, s\n', '<pinned-owner-authentication>', 'exec'), ns)
    return ns


def package():
    raw = (REPOSITORY / 'nox-control/owner_qwen6_backup_stream.py').read_bytes()
    public_raw = (REPOSITORY / 'nox-control/owner_qwen6_backup_public.json').read_bytes()
    core.require(0 < len(raw) <= 128 * 1024 and core.digest(raw) == CORE_SHA, 'EXPORTER_SOURCE_PIN')
    core.require(core.digest(public_raw) == PUBLIC_SHA, 'PUBLIC_METADATA_PIN')
    public = core.document(public_raw)
    core.require(core.digest(public['public_key_pem'].encode()) == PUBLIC_PEM_SHA, 'OWNER_PUBLIC_KEY_PIN')
    core.public_key(public, now=int(time.time()))
    compile(raw, '<qwen6-stream-export>', 'exec')
    return raw, public


class CipherParts:
    def __init__(self, directory):
        self.directory = Path(directory)
        core.require(not any(p.is_symlink() for p in (self.directory.parent, *self.directory.parents)), 'ARTIFACT_PARENT_SYMLINK')
        self.directory.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.mkdir(mode=0o700)
        self.rows, self.stream, self.part_bytes, self.part_hash = [], None, 0, None
        self.total, self.hash = 0, hashlib.sha256()

    def write(self, raw):
        self.total += len(raw); self.hash.update(raw)
        core.require(self.total <= core.MAX_TOTAL + core.MAX_HEADER + 65536, 'CIPHER_TOTAL_BOUND')
        while raw:
            if self.stream is None:
                core.require(len(self.rows) < 13, 'CIPHER_PART_COUNT')
                path = self.directory / f'qwen6-cipher.part{len(self.rows):03d}'
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                self.stream, self.part_hash, self.part_bytes = os.fdopen(fd, 'wb'), hashlib.sha256(), 0
            count = min(len(raw), core.PART_BYTES - self.part_bytes)
            block, raw = raw[:count], raw[count:]
            self.stream.write(block); self.part_hash.update(block); self.part_bytes += len(block)
            if self.part_bytes == core.PART_BYTES:
                self.close_part()

    def close_part(self):
        if self.stream is not None:
            self.stream.flush(); os.fsync(self.stream.fileno()); self.stream.close()
            self.rows.append({'name': f'qwen6-cipher.part{len(self.rows):03d}', 'bytes': self.part_bytes,
                              'sha256': self.part_hash.hexdigest()})
            self.stream = None

    def close(self):
        self.close_part()

    def readback(self):
        h, total = hashlib.sha256(), 0
        for row in self.rows:
            path = self.directory / row['name']
            fd, info = core.open_regular(path.absolute(), core.PART_BYTES)
            try:
                local = hashlib.sha256()
                while True:
                    raw = os.read(fd, core.BLOCK)
                    if not raw:
                        break
                    local.update(raw); h.update(raw); total += len(raw)
                core.checked_fd(fd, path.absolute(), info)
                core.require(info.st_size == row['bytes'] and local.hexdigest() == row['sha256'], 'RUNNER_PART_READBACK')
            finally:
                os.close(fd)
        core.require(total == self.total and h.hexdigest() == self.hash.hexdigest(), 'RUNNER_FULL_READBACK')


def native_script(source, public, commit, run_id):
    # Data-only fixed public metadata; no private key/credential enters native stdin.
    return (source + b'\nraise SystemExit(native_main(' + repr(public).encode() + b', '
            + repr(commit).encode() + b', ' + repr(run_id).encode() + b'))\n')


def receive(common, host, script, public, parts):
    command = common + ['-o', 'ControlMaster=no', '-o', 'ProxyCommand=false', host,
                        'env', 'PYTHONNOUSERSITE=1', '/usr/bin/python3', '-I', '-B', '-']
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr, first, header, selector = bytearray(), bytearray(), None, selectors.DefaultSelector()
    deadline = time.monotonic() + core.MAX_SECONDS + 30
    try:
        # Script is <64KiB; authenticated SSH master already exists.
        core.require(len(script) < 65536, 'NATIVE_SCRIPT_BOUND')
        child.stdin.write(script); child.stdin.close()
        selector.register(child.stdout, selectors.EVENT_READ, 'out')
        selector.register(child.stderr, selectors.EVENT_READ, 'err')
        while selector.get_map():
            core.require(time.monotonic() < deadline, 'TRANSPORT_DEADLINE')
            for key, _ in selector.select(timeout=1):
                raw = os.read(key.fileobj.fileno(), core.BLOCK)
                if not raw:
                    selector.unregister(key.fileobj); continue
                if key.data == 'err':
                    stderr.extend(raw)
                    core.require(len(stderr) <= 128 * 1024, 'NATIVE_DIAGNOSTIC_BOUND')
                elif header is None:
                    first.extend(raw)
                    core.require(len(first) <= core.BLOCK + core.MAX_HEADER, 'HEADER_FIRST_READ_BOUND')
                    if len(first) >= 12:
                        core.require(first[:8] == core.MAGIC, 'NATIVE_MAGIC')
                        length = struct.unpack('>I', first[8:12])[0]
                        core.require(0 < length <= core.MAX_HEADER, 'NATIVE_HEADER_SIZE')
                        if len(first) >= 12 + length:
                            raw_header = bytes(first[12:12 + length])
                            header = core.validate_header(core.document(raw_header, core.MAX_HEADER), public)
                            core.require(core.canonical(header) == raw_header, 'NATIVE_HEADER_CANONICAL')
                            parts.write(bytes(first)); first.clear()
                else:
                    parts.write(raw)
        code = child.wait(timeout=8)
        holds, receipts = [], []
        for line in bytes(stderr).splitlines():
            if line.startswith(b'NOX_QWEN6_EXPORT_HOLD='):
                reason = line.split(b'=', 1)[1].decode('ascii', errors='replace')
                if re.fullmatch('HOLD_QWEN6_BACKUP_[A-Z0-9_]{1,100}', reason):
                    holds.append(reason)
            elif line.startswith(b'NOX_QWEN6_EXPORT='):
                receipts.append(core.document(line.split(b'=', 1)[1], core.MAX_JSON))
        if code != 0 or header is None or len(receipts) != 1:
            raise core.Hold(holds[-1] if holds else 'HOLD_QWEN6_BACKUP_NATIVE_EXPORT_FAILED')
        parts.close()
        native = receipts[0]
        core.require(native.get('ciphertext_sha256') == parts.hash.hexdigest()
                     and native.get('ciphertext_bytes') == parts.total
                     and native.get('all_source_sha256_verified_before_during_after') is True
                     and parts.total == 12 + len(core.canonical(header)) + header['archive_bytes'] + 16,
                     'NATIVE_CIPHER_RECEIPT')
        parts.readback()
        return header, native
    finally:
        selector.close()
        if child.poll() is None:
            child.kill()  # Only this local SSH client; never a native service/process.
            with contextlib.suppress(Exception):
                child.wait(timeout=5)
        parts.close()
        for handle in (child.stdout, child.stderr):
            if handle is not None:
                handle.close()


def cleanup(ns):
    if ns and ns.get('MASTER'):
        with contextlib.suppress(Exception):
            subprocess.run(ns['MASTER'], capture_output=True, timeout=8)
    sys.path.insert(0, str(REPOSITORY))
    from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as helper
    good = helper.cleanup()
    with contextlib.suppress(OSError):
        helper.KEY.unlink()
    return good


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native', action='store_true', required=True)
    parser.parse_args()
    ns, result, failure, authorized = None, None, None, False
    try:
        source, run_id = authorize_event(); authorized = True
        raw, public = package()
        ns = authentication_namespace()
        common, host, _ = ns['run_native']('qwen6-backup', run_id)
        parts = CipherParts(OUTPUT)
        header, native = receive(common, host, native_script(raw, public, source, run_id), public, parts)
        core.require(header['source_sha'] == source and header['workflow_run_id'] == run_id, 'NATIVE_RUN_BINDING')
        result = {'schema': 'NOX_QWEN6_ARTIFACT_RECEIPT_V1', 'state': 'CIPHERTEXT_READY_LOCAL_VERIFICATION_REQUIRED',
                  'scope_sha256': core.scope_sha(), 'source_sha': source, 'workflow_run_id': run_id,
                  'ciphertext_bytes': parts.total, 'ciphertext_sha256': parts.hash.hexdigest(), 'parts': parts.rows,
                  'public_metadata_sha256': core.digest(core.canonical(public)), 'header': header, 'native': native,
                  'runner_plaintext_files_written': 0, 'local_decryption_verified': False, 'drive_copy_verified': False}
    except BaseException as exc:
        reason = str(exc)
        failure = reason if re.fullmatch('HOLD_[A-Z0-9_]{1,120}', reason) else 'HOLD_QWEN6_BACKUP_' + type(exc).__name__.upper()
    finally:
        if authorized and ns is not None:
            try:
                if not cleanup(ns):
                    failure = 'HOLD_QWEN6_BACKUP_TEMPORARY_KEY_CLEANUP'
            except Exception:
                failure = 'HOLD_QWEN6_BACKUP_TEMPORARY_KEY_CLEANUP'
    if failure is not None or result is None:
        print(failure or 'HOLD_QWEN6_BACKUP_NO_RECEIPT'); return 2
    core.require(len(result['parts']) == 7, 'FIXED_WORKFLOW_PART_COUNT')
    target = OUTPUT / 'QWEN6_CIPHER_RECEIPT.json'
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(core.canonical(result) + b'\n'); stream.flush(); os.fsync(stream.fileno())
    print(core.canonical({'state': result['state'], 'parts': len(result['parts']),
                          'ciphertext_bytes': result['ciphertext_bytes'], 'ciphertext_sha256': result['ciphertext_sha256'],
                          'temporary_ssh_key_removed': True, 'local_decryption_verified': False, 'drive_copy_verified': False}).decode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
