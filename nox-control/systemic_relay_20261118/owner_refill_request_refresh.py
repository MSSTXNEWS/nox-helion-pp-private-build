#!/usr/bin/env python3
"""Rebuild one exact REFILL_REQUIRED request from owner-supplied pinned snapshots.

Pure, offline bridge to the EXISTING select_next() and taskpack verifier.
It never claims a task, invokes a model, publishes native work, edits S03,
overrides STOP, changes a source file, or starts another dispatcher.

All four input snapshots require independently recorded exact raw SHA256 pins.
The output is only the selector's validated request, suitable for a subsequent
OWNER_REVIEWED proposal and the existing fenced publisher.
"""
from __future__ import annotations

import argparse
import json

from owner_systemic_taskpack import read_document, _validate_refill_request
from runtime.owner_systemic_refill import SHA, canonical, digest, require, select_next


def load_pinned(path, expected_sha256):
    require(type(expected_sha256) is str and SHA.fullmatch(expected_sha256),
            'REFRESH_INPUT_SHA_FORMAT')
    document, observed_sha256 = read_document(path)
    require(observed_sha256 == expected_sha256, 'REFRESH_INPUT_CHANGED')
    return document


def generate(manifest, manifest_sha256, state_snapshot, source_pins, capacity):
    """Generate only a bounded exact request. Never invent an approval or job."""
    require(type(manifest_sha256) is str and SHA.fullmatch(manifest_sha256),
            'REFRESH_MANIFEST_SHA_FORMAT')
    require(isinstance(manifest, dict) and digest(manifest) == manifest_sha256,
            'REFRESH_MANIFEST_SHA')
    require(isinstance(state_snapshot, dict) and isinstance(source_pins, dict)
            and isinstance(capacity, dict), 'REFRESH_SNAPSHOT_SHAPE')
    require(capacity.get('manifest_sha256') == manifest_sha256,
            'REFRESH_CAPACITY_MANIFEST_SHA')
    selected = select_next(manifest, state_snapshot, source_pins, capacity)
    require(selected.get('state') == 'REFILL_REQUIRED'
            and isinstance(selected.get('refill_request'), dict),
            'REFRESH_NOT_EXHAUSTED')
    request = selected['refill_request']
    # The same exact validation used by the reviewed-taskpack compiler.
    _validate_refill_request(request, manifest, manifest_sha256)
    require(request['original_task_states_sha256'] ==
            digest(request['original_task_states']), 'REFRESH_ORIGINAL_STATE_SHA')
    require(request['original_task_accepted'] is False,
            'REFRESH_NO_ACCEPTANCE')
    return request


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'state-snapshot', 'source-pins', 'capacity'):
        parser.add_argument('--'+name, required=True)
        parser.add_argument('--'+name+'-sha256', required=True)
    args = parser.parse_args(argv)
    manifest = load_pinned(args.manifest, args.manifest_sha256)
    state = load_pinned(args.state_snapshot, args.state_snapshot_sha256)
    pins = load_pinned(args.source_pins, args.source_pins_sha256)
    capacity = load_pinned(args.capacity, args.capacity_sha256)
    request = generate(manifest, args.manifest_sha256, state, pins, capacity)
    print(canonical(request).decode('utf-8'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
