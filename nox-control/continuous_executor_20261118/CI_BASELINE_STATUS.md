# Historical CI baseline and validated compatibility repair

Audit date: 2026-11-18 UTC. The baseline measurement below was taken before the
additive compatibility repair. The baseline inspector had 36 affected methods in
the 137-test required lifeline suite. The compatibility candidate subsequently
passed all 137 unchanged methods and 26 new safety/privacy methods, plus the
related workflow commands listed in `compactci_baseline_report.json`.

Remote verification is now complete on source commit
`db260689c5720a0d1ea654e1a86c03edf91dabcd`:
[Lifeline run 44350542332](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44350542332)
passed all **163** methods, and
[V38 run 44350542287](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44350542287)
passed **177** methods. The machine-readable record is `remote_ci_verification.json`.
These results come from the published source workflows, independently of native
installation receipts. The historical baseline findings below are retained for
provenance and do not assert that the repaired source still fails.

## Exact baseline and cause

The pre-repair `nox-control/owner_native_inspect.py` was byte-identical to that file
at native-lineage commit `0c576e88c7f4ee5ef1c4ff1a8dc438dd5566278a`:

```text
SHA-256: 6b9604ef3d7e4d2123a1f7cceebf452487c5b4b8e5d128a030d517854cfd4525
Size: 22147 bytes; 417 lines
```

The baseline comparison used the then-current file bytes and `git show` at the exact baseline
commit. That baseline file implements queue and process-pool inspection. It does not
provide the earlier `PROC`, `run`, `owner_safety_snapshot`, Maya binary readback,
memory inventory, receipt-privacy, or training-metadata APIs expected by the
existing tests.

The tests load `owner_native_inspect.py` from the expected repository location.
No alternative compatible implementation was found in the current lineage.
This is an API restoration issue, not a wrong test-module path.

## Full required workflow measurement

All nine test commands in
`.github/workflows/nox-native-lifeline-ci.yml` were run locally and independently.
Running the later commands independently exposes failures that the normal
workflow cannot reach after its first failing inspector command. All source
syntax checks specified by the workflow passed.

| Test file | Test methods | Result |
| --- | ---: | --- |
| `test_nox_native_lifeline.py` | 30 | PASS |
| `test_nox_agent_status.py` | 4 | PASS |
| `test_nox_neuro_evolution_ingress.py` | 6 | PASS |
| `test_owner_native_lifeline.py` | 18 | PASS |
| `test_owner_native_audit_mount_inventory.py` | 16 | PASS |
| `test_owner_native_inspect_safety.py` | 18 | 18 errors |
| `test_owner_native_inspect_inventory.py` | 8 | 8 errors |
| `test_owner_native_inspect_receipt_privacy.py` | 10 | 14 error entries, including subtests |
| `test_owner_dispatcher_mentor.py` | 27 | PASS |

Total: **137 test methods; 101 passing methods; 36 methods affected by errors**.
The unittest reports contain **40 error entries** because one failing suite
also reports individual subtest errors. These are missing-API errors, not
successful assertions and not skipped tests.

## Diagnostic legacy control

A compatible inspector exists in the separate feature-lineage checkout at
commit `9b06eef5968ddbbad48f43e5416528565f221640`, with SHA-256
`70f1d29a5c1512d9905c4a98bb2dc0e1d5081214376b855e9801c0699a5a0861`.

For a diagnostic control only, that inspector and the **unchanged current 36
inspector tests** were copied into an isolated temporary directory. All 36
passed. This confirms that the current tests depend on the earlier API.

The repository tests were **not redirected** to the legacy copy, and this
control does not count as fixing current CI. Replacing their subject with a
historical fixture would hide the missing API in the current subject.

## Initial restoration scope and completed candidate validation

Static dependency review found approximately **544 source lines across 27
transitive module functions/constants** needed to restore the tested APIs.
The scope includes:

- Owner STOP aliases, writer-lease non-authorization, Supervisor PID identity,
  and the 8081 listener owner map.
- Original Maya P0 binary SHA and ELF metadata readback.
- Memory/storage metadata inventory and process/GPU identity mapping.
- Privacy-preserving receipt projections, Qwen progress metadata, and strict
  native TRL signature parsing.

The subsequent candidate also restores APIs exercised by related workflows:
pinned Python signature/version probes, controls metadata, mount inventory,
Maya ELF/dependency readback and HF tensor metadata. The final candidate adds
1,154 lines while preserving the original 417 lines, AST bindings and default
`main()`. It includes strict privacy projections, bounded nofollow reads and
PID identity fixes discovered during independent review.

Local validation passed 28 commands / 411 unittest methods, the hybrid helper's
13 HF metadata and 6 signature checks, a 269-file `SOURCE_POLICY_PASS` audit,
and JavaScript syntax checks. The original tests and commands were unchanged;
26 new regression methods were added to the lifeline workflow. The v38 39-test
measurement in this report used the original canonical source; the newly
integrated C02 source is verified separately. No native inspector deployment is
part of this CI compatibility change.
