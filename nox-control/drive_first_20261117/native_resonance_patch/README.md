# Minimal patch for the actual native Resonance page

This package changes the existing page at:

`/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/pc/resonance.html`

It improves header/new-chat/text contrast, measures and offsets the message area when visible headers overlap it, and replaces the hardcoded `LOCAL · … · 127.0.0.1` badge with the address of the page opened in the browser. The badge is a page address, not a claim about connection health, build verification, or the model.

## Scope

The HTML patch consists of four changes: two local asset references, one body flag, and neutral badge text. All original tags, attributes, IDs, data-actions, V24/V25 references and their order remain. Existing STOP, submit, history and backend handlers are unchanged. The new JavaScript does no network requests, inference, storage access or chat event interception. The dark amber theme, original background and scene remain.

The local HTML export contains one extra final LF. Removing exactly that one byte reproduces the recorded native SHA `9a5ee14787f4fc529926576339f86e07ce6ec838fe6e34fe6b2523f102719194` and size 13,785 bytes. The installer accepts only those exact native bytes; it never trims or normalizes the server file.

## Operator commands

`native_minimal_patch.py` embeds both assets and can run standalone through the existing owner repair mechanism. It needs only Python's standard library on Linux. No new service, restart, HTTP request or model access is required.

```sh
python3 native_minimal_patch.py
python3 native_minimal_patch.py --apply
python3 native_minimal_patch.py --rollback
```

The first command is a read-only check. `--site-dir /path/to/site` exists for local fixture testing; production uses the fixed path above.

The installer rejects a changed HTML SHA or conflicting asset contents. Apply creates a verified exact backup, installs the two assets and atomically replaces the HTML after rechecking its SHA. Repeating apply returns `ALREADY_APPLIED` only when HTML, assets and backup all match. Rollback restores the exact backup only if the current HTML is still the expected patched version. It retains the now unreferenced assets to avoid deleting files unnecessarily. An interrupted pre-commit apply may leave the verified backup and unused assets; re-running is safe. A conflicting or partial backup causes HOLD.

Apply and rollback acquire the existing `/root/nox/state/owner_maintenance.lock` with `flock(LOCK_EX | LOCK_NB)`, then the local patch lock. This is the cooperating-writer lease already used by owner maintenance and observed by the native dispatcher. If owner repair already holds that lease, pass its actual open descriptor using `run(..., maintenance_lock_fd=fd)` or `--maintenance-lock-fd`; the inode must match the actual native lock file, and the installer never closes or unlocks the borrowed FD. A missing/busy lock causes HOLD. Local tests override only the lock path in the Python API.

Assets are published using a fsynced temporary file and atomic no-clobber hard link. A late foreign file is preserved and causes HOLD. The backup directory is fsynced before HTML publication. The HTML hash is rechecked under the existing maintenance lease before atomic replacement. This coordinates cooperating native writers, not unrelated editors ignoring that lease: the final hash check and rename are not an operating-system compare-and-swap against an uncooperating external write.

The JSON output starts with `NOX_RESONANCE_PATCH=`. It reports exact file status; `native_ui_verified` remains false because filesystem success is not a browser acceptance test.

## Local verification and remaining acceptance

```sh
python3 -m unittest discover -s tests -p 'test_patch.py' -v
node tests/test_ui.cjs
```

Targeted fixtures check exact backup/apply/idempotency/rollback, stale source/foreign assets/changed rollback refusal, identical original markup and asset order, bounded nonaccumulating geometry and a badge derived only from the page address. This package has not been executed on the native server. The final browser check must confirm visual readability, message/composer geometry, history and STOP with the actual native assets and authorized access. The runtime V24/V25 JavaScript was not changed or replaced. BFCache pagehide preserves observers; pageshow schedules a fresh measurement.
