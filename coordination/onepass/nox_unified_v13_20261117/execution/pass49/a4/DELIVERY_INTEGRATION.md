# Exact GGUF bounded delivery

Task2A03, original role2, same runNOX-49-20261117. Existing verifier and both immutable manifests remain in sibling execution/pass49/role2, unchanged. This helper fills the missing delivery/cursor/atomic-publish implementation. It neither installs a service nor downloads anything by import.

Only after the root lease holder has accepted external backup restoration and persistent-storage admission, supply an existing private0700 staging directory and an explicit measured disk reserve:

```sh
python deliver_gguf_pack.py --stage /admitted/new-stage --byte-budget 67108864 --reserve-bytes 10000000000 --execute
```

Each invocation transfers at most the byte budget (maximum1GiB). Repeat with the same staging path; verified completed files are skipped, incomplete files resume at the fsynced offset with verified prefix SHA. Manifest/revision mismatch, incorrect Range/Content-Range/length/encoding, linked partial data, unexpected existing artifact or corrupted prefix fail closed and preserve bytes. A truncated response retains its last committed cursor. Crash between data fsync and cursor publication is an explicit HOLD requiring reconciliation; this does not silently truncate data. The staging lock serializes only these writes and does not replace the OneHost owner lease.

When ready, provide --publish-to /admitted/new-published as a sibling of stage. Publication happens only after all six payloads pass the existing size/GGUF/SHA verifier and the EnGram alias shares the expected payload. Linux renameat2(RENAME_NOREPLACE) exposes the whole folder atomically without replacing an existing destination, including a race. Existing live weights/pointers are not switched or deleted. The printed receipt can report published=true; the pre-publication on-disk verification receipt conservatively retains published=false. Independent native acceptance still has to verify the resulting directory and exact SHA.

Partial files and cursor sidecars are owned staging data; completed input copies and previous live models are not deleted here. Resident training state is unrelated: these inference GGUF files never qualify as a trainable model revision.

Source acceptance:12 tests PASS using the actual existing verifier, synthetic six-file fixtures, isolated HTTP-range responses and real local fsync/no-replace operations. No network, OneHost transfer, runtime model load, training or native acceptance performed.
