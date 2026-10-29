# R18 Toolkit — source-only execution controls

Python 3.11+ standard library. Run:
```
python -m unittest -v test_nox_flow.py
python nox_flow.py queue registry.json --now 2026-10-29T19:00:00+03:00
python nox_flow.py admit-preview receipt.json registry.json owner_map.json source_dir candidate_dir --head 40hexsha
python nox_flow.py select-tests test_matrix.json Packages/P04/train_qlora.py
python nox_flow.py verify-qa claims.json qa_receipts_dir --head 40hexsha
python nox_flow.py throughput runs.json
python nox_flow.py progress lanes.json
python nox_flow.py gitlab-compare expected.json observed.json
python nox_flow.py component-preview components.json
```

Every action is a LOCAL PREVIEW, not an authenticated PR162 writer or independent QA signature. The test plan does not execute tests. A matching checksum does not prove Git ownership. GitLab compare requires externally authenticated sanitized readback; no token is accepted or transmitted here. Product progress remains N/D without full frozen P01–P05 TaskID inventory and independent current-head QA. Claimed accepted IDs never increase verified throughput. Preserve all 56 rules, SourceLock 729, NO-LOSS, ACL, STOP and native consent. No EXE/NSIS/CI/E07/release before authorization.

Owners: manual #1/T06 sole shared PR162 writer, manual #3 isolated P04/P05 fixes, manual #2 independent QA. T02 sole shared error/lessons journal writer. Read the canonical V16 R18 addendum and use immutable receipts per RunID.