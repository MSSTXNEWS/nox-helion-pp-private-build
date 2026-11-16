# Accepted Qwen checkpoint6 backup

This package is source-only until an explicitly authorized native workflow runs.
It does not claim an existing artifact, a Drive copy, an end-to-end GPU restore,
or a backup of the base model, corpus, S03, chat history or the entire NOX server.

## Exact scope

The fixed checkpoint contains 10 files and 519,882,866 bytes. Its manifest is
`bbe6ff24861fdcf33d28eba089edba583406ffbb9184c68e5a43d305a619b293`;
the accepted restart certificate is
`2076f7050169692e0333747d07abb5c290b429c1b30d56fd55928fc215edfc00`.
The certificate proves six finite optimizer updates with zero skipped updates
and the accepted restart from the earlier five-update checkpoint. This is a
different model and checkpoint from the historical 35B zero-update backup.

Thirteen flat archive members are permitted: the ten checkpoint members,
`checkpoint_manifest.json`, `owner_acceptance.json` and the immutable
`window6_receipt.json`. The checkpoint already contains `lineage.json`, runtime
versions, optimizer, scheduler, scaler, Python and Torch RNG state. No arbitrary
native path can be supplied. No current admission pointer is used to replace
this historical scope if training later advances.

## Native and public boundaries

`owner_qwen6_backup_stream.py` resolves every parent directory without symlinks,
opens only regular files, and bounds the entire selected set before reading large
payloads. All original SHA256 hashes are checked before, while and after streaming.
The final GCM tag is emitted only after the final checks. It streams uncompressed
USTAR directly into AES-256-GCM; the fresh AES key is wrapped using the owner's
RSA4096 public key, OAEP-SHA256 and a scope-specific label. The authenticated header
binds the checkpoint, every member hash and size, source commit, workflow run,
public-key metadata and transfer ID.

The native exporter writes no files, does not load pickle or a model, has no service
or deletion actions, and does not change training flags. It has a 900-second bound,
a 512MiB address-space limit, 1MiB streaming buffers and a 1GiB selected-data bound.
It yields on owner STOP or insufficient cgroup memory. The native training process
continues independently; this export is not a checkpoint writer or a training lease.

`owner_qwen6_backup_runner.py` reuses only the exact reviewed authentication prefix
of the existing owner transport: instance60509551, the existing pinned Ed25519 host
key, one temporary per-instance SSH key and verified cleanup. It never asks for an
unknown owner SSH private key. The remote binary stream is split into seven
ciphertext parts of at most80MiB. Only these files and a small checksum receipt are
eligible for upload. Raw native stderr is suppressed; only categorical failure
codes and bounded public success metadata are printed. Temporary key cleanup must
succeed before the upload receipt is published.

## Explicit manual workflow

The existing V61 workflow keeps `checkpoint_scope=LEGACY` as its default. The Qwen
job requires all of the following: `workflow_dispatch`, the exact repository owner,
`allow_native=YES`, `checkpoint_scope=QWEN6`, and a reviewed40-character `source_sha`
equal to the selected workflow ref's commit. Rerun attempts are rejected. Push runs
source tests only. No secret-bearing export runs on push or pull requests.

The current connector does not expose a workflow-dispatch operation, and the
observed cloud-browser GitHub session was not authenticated. This package does not
bypass that gate. An authenticated manual owner dispatch remains a separate step.
Public-key metadata has a bounded two-hour export window; if it expires before
dispatch, generate a fresh local key and review only the public-metadata/pin update.
The private key belongs only on the owner's local machine, mode0600; it is never a
repository file, workflow input, artifact, server file or log value.

Each of the seven part artifacts contains one fixed ciphertext basename;
the eighth artifact contains `QWEN6_CIPHER_RECEIPT.json`. Download those artifacts
with the existing GitHub artifact tool. Materialize only their expected fixed
ciphertext/receipt member names into a private local directory; reject unexpected
ZIP members, traversal, symlinks or sizes above80MiB (receipt≤256KiB).

## Local verification and durable private Drive copy

The verifier first authenticates the entire GCM stream while discarding plaintext.
Only after that succeeds does a second pass parse the thirteen exact regular USTAR
members and check every original hash. It never extracts a checkpoint or unpickles
optimizer/RNG data. Supply the actual reviewed commit and successful workflow run:

```bash
python3 nox-control/owner_qwen6_backup_local.py \
  --parts-dir /absolute/private/cipher-parts \
  --receipt /absolute/private/cipher-parts/QWEN6_CIPHER_RECEIPT.json \
  --public-meta nox-control/owner_qwen6_backup_public.json \
  --private-key /absolute/private/transfer-key.pem \
  --expected-source REVIEWED_40_CHARACTER_COMMIT \
  --expected-run ACTUAL_WORKFLOW_RUN_ID \
  --restore-dir /absolute/private/new-qwen6-restore
```

The fresh output directory is0700; each plaintext archive part is0600. A verified
`QWEN6_RESTORE_MANIFEST.json` appears only after all checks pass. That manifest records
the full tar hash, every plaintext part hash and every original checkpoint hash.
Upload these plaintext archive parts and their manifest only to the owner's private
Drive folder. The temporary transfer key is not needed to restore that private copy.
Ciphertext on Drive without a recoverable private key is not a durable backup.

After downloading the private Drive parts again, verify them without the transfer key:

```bash
python3 nox-control/owner_qwen6_backup_local.py \
  --parts-dir /absolute/private/drive-readback \
  --restore-manifest /absolute/private/drive-readback/QWEN6_RESTORE_MANIFEST.json \
  --expected-source REVIEWED_40_CHARACTER_COMMIT \
  --expected-run ACTUAL_WORKFLOW_RUN_ID
```

This second mode verifies all part hashes, the full tar hash and every fixed file
against the accepted checkpoint's immutable manifest and certificate. It does not
itself access Drive; the caller must establish that the bytes were freshly fetched
from the recorded Drive file IDs. GPU model/optimizer restart is a separate test.
No source checkpoint is deleted or marked evictable by this package.
