"""Apply the pinned S03 bridge change with the existing owner maintenance transaction."""

import base64
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from types import ModuleType


BUNDLE = __NOX_BUNDLE_JSON__
CONTROL = 'owner_refresh_cognition_c04.py'
HELPER = 'nox_s03_scoped_pair.py'
PATCH = 'native-bridge.patch'
BRIDGE = 'nox_v29_chat_bridge.py'
BRIDGE_PREIMAGE = 'f9163a748c969198b990cd98d7366fa2eaba69eb97c44f5fa8ea4d5d7a10bdcf'
BRIDGE_POSTIMAGE = '3b1f1c22279b2fbca3be03ef53579e8dd93ab3ea44a3c5404e7584f07e3bbf1b'
C04_PIN = '451aa75d323c4429767f8a886300c90941adc59f30b395fec15c1f29b60d3180'
ASSETS = {
    CONTROL: 'fdd6e646c8cef1fad9a6d39afa2723375fa2e6126bf4da4989b751ffc2355de0',
    HELPER: '13334f49c709e1440e5f658b95405136312e5e5c94aad294c7314d96c4206aed',
    PATCH: 'aa8743e1042f8485d0032d35c4a3a956b0eaa48103934c890d2a082fc7933c4d',
}
HUNK = re.compile(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n')


def need(condition, code):
    if not condition:
        raise RuntimeError('HOLD_SCOPED_S03_' + code)


def digest(data):
    return sha256(data).hexdigest()


def bridge_candidate(before, patch):
    need(before is not None and digest(before) == BRIDGE_PREIMAGE, 'BRIDGE_PREIMAGE')
    source = before.decode().splitlines(keepends=True)
    diff = patch.decode().splitlines(keepends=True)
    need(diff[:2] == ['--- a/' + BRIDGE + '\n', '+++ b/' + BRIDGE + '\n'], 'PATCH_SCOPE')
    output, cursor, line = [], 0, 2
    while line < len(diff):
        match = HUNK.fullmatch(diff[line])
        need(match is not None, 'PATCH_HUNK')
        start, old_count, new_start, new_count = map(int, match.groups())
        need(cursor <= start - 1 <= len(source), 'PATCH_OFFSET')
        output.extend(source[cursor:start - 1])
        need(len(output) == new_start - 1, 'PATCH_OUTPUT_OFFSET')
        cursor = start - 1
        line += 1
        read_count = write_count = 0
        while line < len(diff) and not diff[line].startswith('@@ '):
            operation, body = diff[line][:1], diff[line][1:]
            need(operation in (' ', '-', '+'), 'PATCH_OPERATION')
            if operation != '+':
                need(cursor < len(source) and source[cursor] == body, 'PATCH_CONTEXT')
                read_count += 1
                cursor += 1
            if operation != '-':
                output.append(body)
                write_count += 1
            line += 1
        need((read_count, write_count) == (old_count, new_count), 'PATCH_RANGE')
    output.extend(source[cursor:])
    candidate = ''.join(output).encode()
    need(digest(candidate) == BRIDGE_POSTIMAGE, 'BRIDGE_POSTIMAGE')
    compile(candidate, BRIDGE, 'exec')
    return candidate


def maintenance_control(raw):
    # Reuse the exact C04 owner's maintenance, service identity and rollback.
    # Only permit an absent preimage for the newly added S03 helper.
    source = raw.decode()
    anchor = '    def assert_current():'
    need(source.count(anchor) == 1, 'CONTROLLER_LEASE_ANCHOR')
    source = source.replace(anchor, """    acquired = os.fstat(fd)
    trusted(acquired, stat.S_ISREG)
    need(acquired.st_nlink == 1 and inode(acquired) == inode(original), "OWNER_LEASE_INODE")
    original = acquired

    def assert_current():""")
    old = 'need(raw is not None and digest(raw) == PREIMAGE[name], "SOURCE_PREIMAGE")'
    need(source.count(old) == 1, 'CONTROLLER_PREIMAGE')
    source = source.replace(old, 'need(raw is None if PREIMAGE[name] is None else '
                            'raw is not None and digest(raw) == PREIMAGE[name], "SOURCE_PREIMAGE")')
    previous_schema = 'NOX_NATIVE_COGNITION_C04_BOUNDED_TONE_V1'
    need(source.count(previous_schema) == 1, 'CONTROLLER_RECEIPT')
    source = source.replace(previous_schema, 'NOX_NATIVE_S03_SCOPED_PAIR_ACTIVATION_V1')
    controller = ModuleType('owner_scoped_s03_maintenance')
    sys.modules[controller.__name__] = controller
    exec(compile(source, CONTROL, 'exec'), controller.__dict__)
    need(controller.KEEP.get(BRIDGE) == BRIDGE_PREIMAGE, 'CONTROLLER_BRIDGE_PIN')
    controller.KEEP.pop(BRIDGE)
    controller.KEEP['nox_v38_native_context.py'] = C04_PIN
    controller.PREIMAGE = {HELPER: None, BRIDGE: BRIDGE_PREIMAGE}
    controller.STOP += (Path('/root/nox/state/MEMORY_STOP.flag'),)
    return controller


def main():
    need(set(BUNDLE) == set(ASSETS), 'BUNDLE_SCOPE')
    raw = {name: base64.b64decode(value, validate=True) for name, value in BUNDLE.items()}
    need(all(digest(data) == ASSETS[name] for name, data in raw.items()), 'BUNDLE_PIN')
    control = maintenance_control(raw[CONTROL])
    with ExitStack() as stack:
        scripts = control.directory(stack, control.SCRIPTS)
        before, _ = control.read(scripts, BRIDGE)
    after = bridge_candidate(before, raw[PATCH])
    result = control.activate(
        payloads={HELPER: raw[HELPER], BRIDGE: after},
        sha256={HELPER: ASSETS[HELPER], BRIDGE: BRIDGE_POSTIMAGE},
    )
    print('NOX_MAINT_S03_SCOPED_PAIR=' + json.dumps(result, sort_keys=True, separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)


if __name__ == '__main__':
    main()
