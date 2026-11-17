# One current source admission

`CURRENT_SOURCE_MANIFEST.json` is the authoritative source inventory. Its SHA256 is the admission pin for this whole source stage: WEB assets, native bridge, existing dispatcher modules, and the verifier/stager. The older `MINI_SOURCE_MANIFEST.json` and `MINI_RUNTIME_SOURCE_MANIFEST.json` are component receipts, not current admission pins.

`verify_mini_source.py` reads only the current inventory. `stage_current_source.py` optionally copies its exact contents to a **new** directory and re-reads every copy. Supply `--expected-sha256 <current manifest SHA>` with `--stage-to <new directory>`. No destination is overwritten. Default operation is read-only verification. A source drift, unsafe path, symlink, bad Python syntax or incorrect manifest pin stops preparation.

This is source staging, not live installation. No service is stopped or started, no STOP state cleared, no inference/training run, and no database schema applied. `runtime_targets` records the established files under the existing NOX root for a later lease-owner operation. The bridge/ledger use the existing S03 database; schema initialization belongs after the server admission gates, under the owner's lease.

Native admission remains HOLD until the original server has completed ordered STOP, verified external backup and unique-state recovery, storage admission, resource/model checks, then current-SHA deployment and native receipts. Local HTTP fixtures and synthetic STOP receipt events are source evidence only.
